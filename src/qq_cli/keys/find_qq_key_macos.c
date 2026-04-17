#include <dirent.h>
#include <limits.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define MAX_DB_FILES 64
#define CHUNK_SIZE (2 * 1024 * 1024)
#define KEY_MAX_LEN 128

#define CODEC_STORE_PASS_OFF 0x0
#define CODEC_KDF_ITER_OFF 0x4
#define CODEC_KDF_SALT_SZ_OFF 0xc
#define CODEC_KEY_SZ_OFF 0x10
#define CODEC_PAGE_SZ_OFF 0x1c
#define CODEC_KDF_SALT_OFF 0x40
#define CODEC_BTREE_OFF 0x58
#define CODEC_READ_CTX_OFF 0x60
#define CODEC_WRITE_CTX_OFF 0x68

#define CIPHER_KEY_OFF 0x8

#define BTREE_PBT_OFF 0x8
#define BTSHARED_PAGER_OFF 0x0

static const mach_vm_address_t kPagerPathOffsets[] = {0xc8, 0xd0, 0xd8, 0xe0, 0xe8};

typedef struct {
  char path[PATH_MAX];
} db_file_t;

typedef struct {
  char db_path[PATH_MAX];
  char key[KEY_MAX_LEN + 1];
  int key_len;
} scan_result_t;

static void json_print_escaped(const char *value, size_t len) {
  putchar('"');
  for (size_t i = 0; i < len; i++) {
    unsigned char ch = (unsigned char)value[i];
    if (ch == '\\' || ch == '"') {
      putchar('\\');
      putchar((char)ch);
      continue;
    }
    if (ch == '\n') {
      fputs("\\n", stdout);
      continue;
    }
    if (ch == '\r') {
      fputs("\\r", stdout);
      continue;
    }
    if (ch == '\t') {
      fputs("\\t", stdout);
      continue;
    }
    if (ch < 0x20) {
      fprintf(stdout, "\\u%04x", ch);
      continue;
    }
    putchar((char)ch);
  }
  putchar('"');
}

static pid_t find_qq_pid(void) {
  FILE *fp = popen("pgrep -x QQ", "r");
  if (!fp) {
    return -1;
  }
  char buf[64];
  pid_t pid = -1;
  if (fgets(buf, sizeof(buf), fp)) {
    pid = (pid_t)atoi(buf);
  }
  pclose(fp);
  return pid;
}

static int load_db_files(const char *db_dir, db_file_t *db_files, int *db_count) {
  DIR *dir = opendir(db_dir);
  if (!dir) {
    return -1;
  }

  int count = 0;
  struct dirent *ent;
  while ((ent = readdir(dir)) != NULL) {
    if (ent->d_name[0] == '.') {
      continue;
    }
    size_t len = strlen(ent->d_name);
    if (len < 3 || strcmp(ent->d_name + len - 3, ".db") != 0) {
      continue;
    }
    if (count >= MAX_DB_FILES) {
      break;
    }

    char full_path[PATH_MAX];
    if (snprintf(full_path, sizeof(full_path), "%s/%s", db_dir, ent->d_name) >= (int)sizeof(full_path)) {
      continue;
    }

    struct stat st;
    if (stat(full_path, &st) != 0 || !S_ISREG(st.st_mode)) {
      continue;
    }

    memset(&db_files[count], 0, sizeof(db_files[count]));
    strncpy(db_files[count].path, full_path, sizeof(db_files[count].path) - 1);
    count++;
  }

  closedir(dir);
  *db_count = count;
  return 0;
}

static int read_process(task_t task, mach_vm_address_t addr, void *buffer, mach_vm_size_t size) {
  mach_vm_size_t out_size = 0;
  kern_return_t kr = mach_vm_read_overwrite(task, addr, size, (mach_vm_address_t)buffer, &out_size);
  return kr == KERN_SUCCESS && out_size == size;
}

static int read_u64(task_t task, mach_vm_address_t addr, uint64_t *value) {
  return read_process(task, addr, value, sizeof(*value));
}

static int read_i32(task_t task, mach_vm_address_t addr, int32_t *value) {
  return read_process(task, addr, value, sizeof(*value));
}

static int read_c_string(task_t task, mach_vm_address_t addr, char *buf, size_t buf_len) {
  if (addr == 0 || buf_len == 0) {
    return 0;
  }
  if (!read_process(task, addr, buf, (mach_vm_size_t)(buf_len - 1))) {
    return 0;
  }
  buf[buf_len - 1] = '\0';
  char *nul = memchr(buf, '\0', buf_len - 1);
  if (!nul) {
    return 0;
  }
  return 1;
}

static int is_valid_key_size(int value) {
  return value == 16 || value == 24 || value == 32 || value == 48 || value == 64;
}

static int is_valid_page_size(int value) {
  return value == 1024 || value == 2048 || value == 4096 || value == 8192 || value == 16384;
}

static int read_bytes(task_t task, uint64_t ptr, unsigned char *buf, int len) {
  if (ptr == 0 || len <= 0 || len > KEY_MAX_LEN) {
    return 0;
  }
  return read_process(task, (mach_vm_address_t)ptr, buf, (mach_vm_size_t)len);
}

static int buffer_all_zero(const unsigned char *buf, int len) {
  for (int i = 0; i < len; i++) {
    if (buf[i] != 0) {
      return 0;
    }
  }
  return 1;
}

static void hex_encode(const unsigned char *src, int len, char *dst) {
  static const char kHex[] = "0123456789abcdef";
  for (int i = 0; i < len; i++) {
    dst[i * 2] = kHex[(src[i] >> 4) & 0xF];
    dst[i * 2 + 1] = kHex[src[i] & 0xF];
  }
  dst[len * 2] = '\0';
}

static int build_keyspec(task_t task, uint64_t codec_ptr, uint64_t read_ctx, uint64_t write_ctx,
                         int32_t key_sz, char *out_key, int *out_len) {
  int32_t kdf_salt_sz = 0;
  uint64_t kdf_salt_ptr = 0;
  uint64_t read_key_ptr = 0;
  uint64_t write_key_ptr = 0;
  unsigned char key_buf[KEY_MAX_LEN];
  unsigned char write_key_buf[KEY_MAX_LEN];
  unsigned char salt_buf[KEY_MAX_LEN];

  if (!read_i32(task, (mach_vm_address_t)(codec_ptr + CODEC_KDF_SALT_SZ_OFF), &kdf_salt_sz)) {
    return 0;
  }
  if (kdf_salt_sz <= 0 || kdf_salt_sz > KEY_MAX_LEN) {
    return 0;
  }
  if (!read_u64(task, (mach_vm_address_t)(codec_ptr + CODEC_KDF_SALT_OFF), &kdf_salt_ptr) || kdf_salt_ptr == 0) {
    return 0;
  }
  if (!read_u64(task, (mach_vm_address_t)(read_ctx + CIPHER_KEY_OFF), &read_key_ptr) || read_key_ptr == 0) {
    return 0;
  }
  if (!read_u64(task, (mach_vm_address_t)(write_ctx + CIPHER_KEY_OFF), &write_key_ptr) || write_key_ptr == 0) {
    return 0;
  }
  if (!read_bytes(task, read_key_ptr, key_buf, key_sz)) {
    return 0;
  }
  if (!read_bytes(task, write_key_ptr, write_key_buf, key_sz)) {
    return 0;
  }
  if (!read_bytes(task, kdf_salt_ptr, salt_buf, kdf_salt_sz)) {
    return 0;
  }
  if (buffer_all_zero(key_buf, key_sz) || buffer_all_zero(salt_buf, kdf_salt_sz)) {
    return 0;
  }
  if (memcmp(key_buf, write_key_buf, (size_t)key_sz) != 0) {
    return 0;
  }

  char key_hex[(KEY_MAX_LEN * 2) + 1];
  char salt_hex[(KEY_MAX_LEN * 2) + 1];
  hex_encode(key_buf, key_sz, key_hex);
  hex_encode(salt_buf, kdf_salt_sz, salt_hex);
  int n = snprintf(out_key, KEY_MAX_LEN + 1, "x'%s%s'", key_hex, salt_hex);
  if (n <= 0 || n > KEY_MAX_LEN) {
    return 0;
  }
  *out_len = n;
  return 1;
}

static int validate_codec(task_t task, uint64_t codec_ptr, char *out_key, int *out_len, uint64_t *out_btree_ptr) {
  int32_t store_pass = 0;
  int32_t kdf_iter = 0;
  int32_t key_sz = 0;
  int32_t page_sz = 0;
  uint64_t btree_ptr = 0;
  uint64_t read_ctx = 0;
  uint64_t write_ctx = 0;

  if (!read_i32(task, (mach_vm_address_t)(codec_ptr + CODEC_STORE_PASS_OFF), &store_pass)) {
    return 0;
  }
  if (!read_i32(task, (mach_vm_address_t)(codec_ptr + CODEC_KDF_ITER_OFF), &kdf_iter)) {
    return 0;
  }
  if (!read_i32(task, (mach_vm_address_t)(codec_ptr + CODEC_KEY_SZ_OFF), &key_sz)) {
    return 0;
  }
  if (!read_i32(task, (mach_vm_address_t)(codec_ptr + CODEC_PAGE_SZ_OFF), &page_sz)) {
    return 0;
  }
  if (!read_u64(task, (mach_vm_address_t)(codec_ptr + CODEC_BTREE_OFF), &btree_ptr) || btree_ptr == 0) {
    return 0;
  }
  if (!read_u64(task, (mach_vm_address_t)(codec_ptr + CODEC_READ_CTX_OFF), &read_ctx) || read_ctx == 0) {
    return 0;
  }
  if (!read_u64(task, (mach_vm_address_t)(codec_ptr + CODEC_WRITE_CTX_OFF), &write_ctx) || write_ctx == 0) {
    return 0;
  }

  if (store_pass < 0 || store_pass > 1) {
    return 0;
  }
  if (kdf_iter < 1000 || kdf_iter > 1000000) {
    return 0;
  }
  if (!is_valid_key_size(key_sz) || !is_valid_page_size(page_sz)) {
    return 0;
  }

  if (!build_keyspec(task, codec_ptr, read_ctx, write_ctx, key_sz, out_key, out_len)) {
    return 0;
  }

  *out_btree_ptr = btree_ptr;
  return 1;
}

static int match_db_path(const char *path, const db_file_t *db_files, int db_count) {
  for (int i = 0; i < db_count; i++) {
    if (strcmp(path, db_files[i].path) == 0) {
      return 1;
    }
  }
  return 0;
}

static int resolve_db_path(task_t task, uint64_t btree_ptr, const db_file_t *db_files, int db_count, char *out_path, size_t out_len) {
  uint64_t btshared_ptr = 0;
  uint64_t pager_ptr = 0;
  if (!read_u64(task, (mach_vm_address_t)(btree_ptr + BTREE_PBT_OFF), &btshared_ptr) || btshared_ptr == 0) {
    return 0;
  }
  if (!read_u64(task, (mach_vm_address_t)(btshared_ptr + BTSHARED_PAGER_OFF), &pager_ptr) || pager_ptr == 0) {
    return 0;
  }

  for (size_t i = 0; i < sizeof(kPagerPathOffsets) / sizeof(kPagerPathOffsets[0]); i++) {
    uint64_t path_ptr = 0;
    if (!read_u64(task, (mach_vm_address_t)(pager_ptr + kPagerPathOffsets[i]), &path_ptr) || path_ptr == 0) {
      continue;
    }
    char path_buf[PATH_MAX];
    if (!read_c_string(task, (mach_vm_address_t)path_ptr, path_buf, sizeof(path_buf))) {
      continue;
    }
    if (!match_db_path(path_buf, db_files, db_count)) {
      continue;
    }
    strncpy(out_path, path_buf, out_len - 1);
    out_path[out_len - 1] = '\0';
    return 1;
  }

  return 0;
}

static int scan_for_live_key(task_t task, const db_file_t *db_files, int db_count, scan_result_t *result) {
  unsigned char *buffer = malloc(CHUNK_SIZE);
  if (!buffer) {
    return -1;
  }

  mach_vm_address_t addr = 0;
  while (1) {
    mach_vm_size_t region_size = 0;
    vm_region_basic_info_data_64_t info;
    mach_msg_type_number_t info_count = VM_REGION_BASIC_INFO_COUNT_64;
    mach_port_t object_name = MACH_PORT_NULL;
    kern_return_t kr = mach_vm_region(task, &addr, &region_size, VM_REGION_BASIC_INFO_64,
                                      (vm_region_info_t)&info, &info_count, &object_name);
    if (kr != KERN_SUCCESS) {
      break;
    }
    if (region_size == 0) {
      addr++;
      continue;
    }

    if ((info.protection & (VM_PROT_READ | VM_PROT_WRITE)) == (VM_PROT_READ | VM_PROT_WRITE)) {
      mach_vm_address_t cursor = addr;
      while (cursor < addr + region_size) {
        mach_vm_size_t chunk = (addr + region_size) - cursor;
        if (chunk > CHUNK_SIZE) {
          chunk = CHUNK_SIZE;
        }
        if (read_process(task, cursor, buffer, chunk)) {
          size_t start = (size_t)((8 - (cursor & 7)) & 7);
          for (size_t i = start; i + CODEC_WRITE_CTX_OFF + sizeof(uint64_t) <= (size_t)chunk; i += 8) {
            int32_t store_pass = 0;
            int32_t kdf_iter = 0;
            int32_t key_sz = 0;
            int32_t page_sz = 0;
            uint64_t btree_ptr = 0;
            uint64_t read_ctx = 0;
            uint64_t write_ctx = 0;

            memcpy(&store_pass, buffer + i + CODEC_STORE_PASS_OFF, sizeof(store_pass));
            memcpy(&kdf_iter, buffer + i + CODEC_KDF_ITER_OFF, sizeof(kdf_iter));
            memcpy(&key_sz, buffer + i + CODEC_KEY_SZ_OFF, sizeof(key_sz));
            memcpy(&page_sz, buffer + i + CODEC_PAGE_SZ_OFF, sizeof(page_sz));
            memcpy(&btree_ptr, buffer + i + CODEC_BTREE_OFF, sizeof(btree_ptr));
            memcpy(&read_ctx, buffer + i + CODEC_READ_CTX_OFF, sizeof(read_ctx));
            memcpy(&write_ctx, buffer + i + CODEC_WRITE_CTX_OFF, sizeof(write_ctx));

            if (store_pass < 0 || store_pass > 1) {
              continue;
            }
            if (kdf_iter < 1000 || kdf_iter > 1000000) {
              continue;
            }
            if (!is_valid_key_size(key_sz) || !is_valid_page_size(page_sz)) {
              continue;
            }
            if (btree_ptr == 0 || read_ctx == 0 || write_ctx == 0) {
              continue;
            }

            uint64_t codec_ptr = cursor + (mach_vm_address_t)i;
            char key[KEY_MAX_LEN + 1];
            int key_len = 0;
            uint64_t live_btree_ptr = 0;
            if (!validate_codec(task, codec_ptr, key, &key_len, &live_btree_ptr)) {
              continue;
            }

            char path[PATH_MAX];
            if (!resolve_db_path(task, live_btree_ptr, db_files, db_count, path, sizeof(path))) {
              continue;
            }

            strncpy(result->db_path, path, sizeof(result->db_path) - 1);
            result->db_path[sizeof(result->db_path) - 1] = '\0';
            strncpy(result->key, key, sizeof(result->key) - 1);
            result->key[sizeof(result->key) - 1] = '\0';
            result->key_len = key_len;
            free(buffer);
            return 0;
          }
        }
        if (chunk <= CODEC_WRITE_CTX_OFF) {
          break;
        }
        cursor += (mach_vm_address_t)(chunk - CODEC_WRITE_CTX_OFF);
      }
    }

    addr += region_size;
  }

  free(buffer);
  return 1;
}

int main(int argc, char *argv[]) {
  pid_t pid = 0;
  const char *db_dir = NULL;

  if (argc >= 2) {
    pid = (pid_t)atoi(argv[1]);
  } else {
    pid = find_qq_pid();
  }
  if (argc >= 3) {
    db_dir = argv[2];
  }

  if (pid <= 0) {
    fprintf(stderr, "QQ not running or invalid PID\n");
    return 2;
  }
  if (!db_dir || db_dir[0] == '\0') {
    fprintf(stderr, "db_dir is required\n");
    return 2;
  }

  db_file_t db_files[MAX_DB_FILES];
  int db_count = 0;
  if (load_db_files(db_dir, db_files, &db_count) != 0 || db_count == 0) {
    fprintf(stderr, "no database files found under %s\n", db_dir);
    return 3;
  }

  mach_port_t task = MACH_PORT_NULL;
  kern_return_t kr = task_for_pid(mach_task_self(), pid, &task);
  if (kr != KERN_SUCCESS) {
    fprintf(stderr, "task_for_pid failed: %d\n", kr);
    return 4;
  }

  scan_result_t result;
  memset(&result, 0, sizeof(result));
  if (scan_for_live_key(task, db_files, db_count, &result) != 0 || result.key_len <= 0) {
    fprintf(stderr, "no live codec context matched target dbs\n");
    return 6;
  }

  fputs("{\"method\":\"c_scan\",\"db_path\":", stdout);
  json_print_escaped(result.db_path, strlen(result.db_path));
  fputs(",\"key\":", stdout);
  json_print_escaped(result.key, (size_t)result.key_len);
  fprintf(stdout, ",\"key_len\":%d}\n", result.key_len);
  return 0;
}
