/*
 * crd-installer.c — Chrome Remote Desktop installer for any Linux distro
 *
 * Compiles to a single static binary. Auto-checks for the latest CRD version
 * from Google's download endpoint, installs, configures, and creates a
 * systemd service. Can self-update by re-downloading the latest CRD package.
 *
 * Build:
 *   gcc -o crd-installer crd-installer.c -static -O2 -lpthread
 *   # or without static:
 *   gcc -o crd-installer crd-installer.c -O2 -lpthread
 *
 * Usage:
 *   ./crd-installer                    Interactive install
 *   ./crd-installer --code="4/0AXx..." Install with OAuth code
 *   ./crd-installer --update           Update CRD to latest version
 *   ./crd-installer --status           Show service status
 *   ./crd-installer --uninstall        Remove CRD
 *   ./crd-installer --help             Show help
 *
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/utsname.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/stat.h>
#include <dirent.h>
#include <ctype.h>
#include <errno.h>
#include <pwd.h>

/* ─── Colors ──────────────────────────────────────────────────────── */
#define RED     "\033[0;31m"
#define GREEN   "\033[0;32m"
#define YELLOW  "\033[1;33m"
#define CYAN    "\033[0;36m"
#define BOLD    "\033[1m"
#define NC      "\033[0m"

/* ─── Constants ───────────────────────────────────────────────────── */
#define CRD_DOWNLOAD_URL_BASE "https://dl.google.com/linux/direct/chrome-remote-desktop_current_"
#define CRD_VERSION_CHECK_URL "https://dl.google.com/linux/direct/chrome-remote-desktop_current_amd64.deb"
#define CRD_INSTALL_DIR "/opt/google/chrome-remote-desktop"
#define CRD_CONFIG_DIR_FORMAT "%s/.config/chrome-remote-desktop"
#define CRD_SERVICE_PATH "/etc/systemd/system/crd-host.service"
#define MAX_BUF 8192
#define MAX_LINE 4096

/* ─── Logging ─────────────────────────────────────────────────────── */
static void log_info(const char *msg)  { printf(GREEN "[CRD]" NC " %s\n", msg); }
static void log_warn(const char *msg)  { printf(YELLOW "[CRD]" NC " %s\n", msg); }
static void log_err(const char *msg)   { printf(RED "[CRD]" NC " %s\n", msg); }
static void log_step(int step, int total, const char *msg) {
    printf(CYAN "[CRD]" NC " Step %d/%d: %s\n", step, total, msg);
}

/* ─── String helpers ──────────────────────────────────────────────── */
static char *str_dup(const char *s) {
    char *d = malloc(strlen(s) + 1);
    if (d) strcpy(d, s);
    return d;
}

static int starts_with(const char *str, const char *prefix) {
    return strncmp(str, prefix, strlen(prefix)) == 0;
}

static int ends_with(const char *str, const char *suffix) {
    size_t len_str = strlen(str), len_suf = strlen(suffix);
    if (len_suf > len_str) return 0;
    return strcmp(str + len_str - len_suf, suffix) == 0;
}

static void trim(char *s) {
    char *p = s;
    while (isspace(*p)) p++;
    if (p != s) memmove(s, p, strlen(p) + 1);
    p = s + strlen(s) - 1;
    while (p >= s && isspace(*p)) *p-- = '\0';
}

/* ─── Shell execution ─────────────────────────────────────────────── */
static int run(const char *cmd) {
    int ret = system(cmd);
    return WIFEXITED(ret) ? WEXITSTATUS(ret) : -1;
}

static int run_capture(const char *cmd, char *output, size_t outlen) {
    FILE *fp = popen(cmd, "r");
    if (!fp) return -1;
    size_t total = 0;
    char line[MAX_LINE];
    output[0] = '\0';
    while (fgets(line, sizeof(line), fp) && total < outlen - 1) {
        size_t len = strlen(line);
        if (total + len >= outlen - 1) len = outlen - 1 - total;
        strncat(output, line, len);
        total += len;
    }
    pclose(fp);
    return 0;
}

static int sudo_prefix(char *buf, size_t buflen) {
    if (geteuid() == 0) { buf[0] = '\0'; return 0; }
    if (system("command -v sudo &>/dev/null") == 0) {
        strncpy(buf, "sudo ", buflen);
        return 0;
    }
    log_err("Need root or sudo access");
    return -1;
}

/* ─── Distro detection ────────────────────────────────────────────── */
typedef enum {
    DISTRO_DEBIAN,   /* ubuntu, debian, mint, pop */
    DISTRO_FEDORA,   /* fedora, rhel, centos, rocky, alma, nobara */
    DISTRO_ARCH,     /* arch, manjaro, endeavouros */
    DISTRO_SUSE,     /* opensuse, suse */
    DISTRO_UNKNOWN
} distro_t;

static distro_t detect_distro(void) {
    FILE *fp = fopen("/etc/os-release", "r");
    if (!fp) {
        if (fopen("/etc/debian_version", "r")) return DISTRO_DEBIAN;
        if (fopen("/etc/redhat-release", "r")) return DISTRO_FEDORA;
        return DISTRO_UNKNOWN;
    }
    char line[MAX_LINE];
    char id[256] = "";
    while (fgets(line, sizeof(line), fp)) {
        if (starts_with(line, "ID=")) {
            sscanf(line, "ID=\"%255[^\"]\"", id);
            if (strlen(id) == 0) sscanf(line, "ID=%255s", id);
            break;
        }
    }
    fclose(fp);

    if (strstr(id, "ubuntu") || strstr(id, "debian") ||
        strstr(id, "mint") || strstr(id, "pop") || strstr(id, "linuxmint"))
        return DISTRO_DEBIAN;
    if (strstr(id, "fedora") || strstr(id, "rhel") || strstr(id, "centos") ||
        strstr(id, "rocky") || strstr(id, "alma") || strstr(id, "nobara"))
        return DISTRO_FEDORA;
    if (strstr(id, "arch") || strstr(id, "manjaro") || strstr(id, "endeavour"))
        return DISTRO_ARCH;
    if (strstr(id, "suse") || strstr(id, "opensuse"))
        return DISTRO_SUSE;
    return DISTRO_UNKNOWN;
}

static const char *distro_name(distro_t d) {
    switch (d) {
        case DISTRO_DEBIAN: return "Debian/Ubuntu";
        case DISTRO_FEDORA: return "Fedora/RHEL";
        case DISTRO_ARCH:   return "Arch";
        case DISTRO_SUSE:   return "SUSE";
        default:            return "Unknown";
    }
}

/* ─── Architecture detection ─────────────────────────────────────── */
static const char *detect_arch_deb(void) {
    struct utsname u;
    uname(&u);
    if (strcmp(u.machine, "x86_64") == 0 || strcmp(u.machine, "amd64") == 0)
        return "amd64";
    if (strcmp(u.machine, "aarch64") == 0 || strcmp(u.machine, "arm64") == 0)
        return "arm64";
    return NULL;
}

/* ─── HTTP download (via wget/curl) ───────────────────────────────── */
static int download_file(const char *url, const char *dest) {
    char cmd[MAX_BUF];
    if (system("command -v wget &>/dev/null") == 0) {
        snprintf(cmd, sizeof(cmd), "wget -q --show-progress -O %s %s", dest, url);
        return run(cmd);
    }
    if (system("command -v curl &>/dev/null") == 0) {
        snprintf(cmd, sizeof(cmd), "curl -sL -o %s %s", dest, url);
        return run(cmd);
    }
    log_err("Need wget or curl installed");
    return -1;
}

/* ─── Get remote version (from HTTP headers) ──────────────────────── */
static int get_remote_version(char *version, size_t vlen) {
    char cmd[MAX_BUF];
    char output[MAX_BUF] = "";

    /* Use curl -sI to get headers, extract Last-Modified or etag */
    if (system("command -v curl &>/dev/null") == 0) {
        snprintf(cmd, sizeof(cmd),
            "curl -sI %schrome-remote-desktop_current_amd64.deb 2>/dev/null", CRD_DOWNLOAD_URL_BASE);
        run_capture(cmd, output, sizeof(output));

        /* Try to extract version from redirect or content-disposition */
        char *line = strtok(output, "\n");
        while (line) {
            if (strcasestr(line, "location:") || strcasestr(line, "content-disposition:")) {
                /* Look for version pattern like 152.0.7977.9 */
                char *p = line;
                while (*p) {
                    if (isdigit(*p) && isdigit(*(p+1)) && *(p+2) == '.') {
                        size_t i = 0;
                        while (i < vlen - 1 && (isdigit(*p) || *p == '.')) {
                            version[i++] = *p++;
                        }
                        version[i] = '\0';
                        /* Trim trailing dots */
                        while (i > 0 && version[i-1] == '.') version[--i] = '\0';
                        return 0;
                    }
                    p++;
                }
            }
            line = strtok(NULL, "\n");
        }
    }

    /* Fallback: get version from installed package */
    snprintf(version, vlen, "unknown");
    return -1;
}

/* ─── Get installed version ───────────────────────────────────────── */
static int get_installed_version(char *version, size_t vlen) {
    char path[MAX_BUF];
    snprintf(path, sizeof(path), "%s/chrome-remote-desktop-host", CRD_INSTALL_DIR);

    if (access(path, X_OK) != 0) {
        snprintf(version, vlen, "not-installed");
        return -1;
    }

    /* Try reading version from the host binary output or a version file */
    char cmd[MAX_BUF];
    char output[MAX_BUF] = "";

    /* Check if there's a version string in the binary */
    snprintf(cmd, sizeof(cmd),
        "strings %s/chrome-remote-desktop-host 2>/dev/null | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+' | head -1",
        CRD_INSTALL_DIR);
    if (run_capture(cmd, output, sizeof(output)) == 0) {
        trim(output);
        if (strlen(output) > 0) {
            strncpy(version, output, vlen - 1);
            version[vlen - 1] = '\0';
            return 0;
        }
    }

    /* Fallback: check dpkg/rpm */
    snprintf(cmd, sizeof(cmd), "dpkg -l chrome-remote-desktop 2>/dev/null | grep chrome | awk '{print $3}'");
    if (run_capture(cmd, output, sizeof(output)) == 0) {
        trim(output);
        if (strlen(output) > 0) {
            strncpy(version, output, vlen - 1);
            version[vlen - 1] = '\0';
            return 0;
        }
    }

    snprintf(version, vlen, "unknown");
    return -1;
}

/* ─── Install dependencies ────────────────────────────────────────── */
static int install_deps(distro_t distro) {
    char sudo[MAX_BUF];
    if (sudo_prefix(sudo, sizeof(sudo)) < 0) return -1;
    char cmd[MAX_BUF];

    switch (distro) {
        case DISTRO_DEBIAN:
            snprintf(cmd, sizeof(cmd), "%sapt-get update -qq && %sapt-get install -y -qq wget ar xdg-utils binutils", sudo, sudo);
            break;
        case DISTRO_FEDORA:
            snprintf(cmd, sizeof(cmd), "%sdnf install -y -q wget xdg-utils binutils dpkg", sudo);
            break;
        case DISTRO_ARCH:
            snprintf(cmd, sizeof(cmd), "%spacman -Sy --noconfirm wget xdg-utils dpkg binutils", sudo);
            break;
        case DISTRO_SUSE:
            snprintf(cmd, sizeof(cmd), "%szypper -q install wget xdg-utils dpkg binutils", sudo);
            break;
        default:
            log_warn("Unknown distro — skipping dependency install");
            return 0;
    }
    return run(cmd);
}

/* ─── Download CRD ─────────────────────────────────────────────────── */
static int download_crd(const char *arch_deb, const char *dest) {
    char url[MAX_BUF];
    snprintf(url, sizeof(url), "%s%s.deb", CRD_DOWNLOAD_URL_BASE, arch_deb);
    log_info("Downloading Chrome Remote Desktop...");
    printf("  URL: %s\n", url);
    return download_file(url, dest);
}

/* ─── Install CRD ─────────────────────────────────────────────────── */
static int install_crd(distro_t distro, const char *deb_file) {
    char sudo[MAX_BUF];
    if (sudo_prefix(sudo, sizeof(sudo)) < 0) return -1;
    char cmd[MAX_BUF];

    if (distro == DISTRO_DEBIAN) {
        snprintf(cmd, sizeof(cmd), "%sapt-get install -y -q %s", sudo, deb_file);
        return run(cmd);
    }

    /* For non-Debian: extract and copy manually */
    log_info("Extracting CRD package...");
    char tmpdir[] = "/tmp/crd-install-XXXXXX";
    mkdtemp(tmpdir);

    /* Extract .deb */
    if (system("command -v dpkg-deb &>/dev/null") == 0) {
        snprintf(cmd, sizeof(cmd), "dpkg-deb -x %s %s", deb_file, tmpdir);
    } else {
        snprintf(cmd, sizeof(cmd), "cd %s && ar x %s && tar xf data.tar.* 2>/dev/null || tar xf data.tar.xz 2>/dev/null || tar xf data.tar.gz 2>/dev/null", tmpdir, deb_file);
    }
    if (run(cmd) != 0) {
        log_err("Failed to extract .deb package");
        return -1;
    }

    /* Copy to /opt/google/chrome-remote-desktop/ */
    char src[MAX_BUF], dst[MAX_BUF];
    snprintf(src, sizeof(src), "%s/opt/google/chrome-remote-desktop", tmpdir);
    snprintf(dst, sizeof(dst), "%s", CRD_INSTALL_DIR);

    snprintf(cmd, sizeof(cmd), "%smkdir -p %s", sudo, dst);
    run(cmd);

    snprintf(cmd, sizeof(cmd), "%scp -r %s/* %s/ 2>/dev/null", sudo, src, dst);
    if (run(cmd) != 0) {
        log_err("Failed to copy CRD files");
        return -1;
    }

    /* Copy usr/bin if present */
    snprintf(cmd, sizeof(cmd), "%scp -r %s/usr/bin/* /usr/bin/ 2>/dev/null || true", sudo, tmpdir);
    run(cmd);

    /* Copy usr/share if present */
    snprintf(cmd, sizeof(cmd), "%scp -r %s/usr/share/* /usr/share/ 2>/dev/null || true", sudo, tmpdir);
    run(cmd);

    /* Verify */
    char check[MAX_BUF];
    snprintf(check, sizeof(check), "%s/start-host", CRD_INSTALL_DIR);
    if (access(check, F_OK) != 0) {
        log_err("Installation failed — start-host not found");
        return -1;
    }

    /* Cleanup */
    snprintf(cmd, sizeof(cmd), "rm -rf %s", tmpdir);
    run(cmd);

    log_info("CRD installed to /opt/google/chrome-remote-desktop/");
    return 0;
}

/* ─── Create systemd service ──────────────────────────────────────── */
static int create_service(void) {
    char sudo[MAX_BUF];
    if (sudo_prefix(sudo, sizeof(sudo)) < 0) return -1;

    const char *user = getenv("SUDO_USER");
    if (!user) user = getenv("USER");
    if (!user) user = "root";

    /* Get home dir */
    char home[MAX_BUF];
    struct passwd *pw = getpwnam(user);
    if (pw) {
        strncpy(home, pw->pw_dir, sizeof(home) - 1);
        home[sizeof(home) - 1] = '\0';
    } else {
        snprintf(home, sizeof(home), "/home/%s", user);
    }

    const char *display = getenv("DISPLAY");
    if (!display) display = ":0";

    /* Write service file to /tmp first, then sudo cp */
    FILE *f = fopen("/tmp/crd-host-service.tmp", "w");
    if (!f) {
        log_err("Failed to create temp service file");
        return -1;
    }

    fprintf(f,
        "[Unit]\n"
        "Description=Chrome Remote Desktop Host\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        "User=%s\n"
        "Environment=DISPLAY=%s\n"
        "ExecStart=%s/chrome-remote-desktop-host --console\n"
        "Restart=always\n"
        "RestartSec=10\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n",
        user, display, CRD_INSTALL_DIR);

    fclose(f);

    char cmd[MAX_BUF];
    snprintf(cmd, sizeof(cmd), "%scp /tmp/crd-host-service.tmp %s", sudo, CRD_SERVICE_PATH);
    if (run(cmd) != 0) {
        log_err("Failed to install service file");
        return -1;
    }

    snprintf(cmd, sizeof(cmd), "%ssystemctl daemon-reload", sudo);
    run(cmd);

    remove("/tmp/crd-host-service.tmp");
    log_info("System service created: crd-host.service");
    return 0;
}

/* ─── Configure host ──────────────────────────────────────────────── */
static int configure_host(const char *oauth_code) {
    const char *user = getenv("SUDO_USER");
    if (!user) user = getenv("USER");
    if (!user) user = "root";

    struct passwd *pw = getpwnam(user);
    char home[MAX_BUF];
    if (pw) {
        strncpy(home, pw->pw_dir, sizeof(home) - 1);
        home[sizeof(home) - 1] = '\0';
    } else {
        snprintf(home, sizeof(home), "/home/%s", user);
    }

    char config_dir[MAX_BUF];
    snprintf(config_dir, sizeof(config_dir), "%s/.config/chrome-remote-desktop", home);

    /* Create config dir */
    char cmd[MAX_BUF];
    snprintf(cmd, sizeof(cmd), "mkdir -p %s", config_dir);
    run(cmd);

    /* Check if already configured */
    char host_json[MAX_BUF];
    snprintf(host_json, sizeof(host_json), "%s/host.json", config_dir);

    if (access(host_json, F_OK) == 0) {
        log_info("Host already configured — using existing config");
        return 0;
    }

    /* Check for host#*.json files */
    char ls_cmd[MAX_BUF];
    snprintf(ls_cmd, sizeof(ls_cmd), "ls %s/host#*.json 2>/dev/null | head -1", config_dir);
    char existing[MAX_BUF] = "";
    run_capture(ls_cmd, existing, sizeof(existing));
    trim(existing);

    if (strlen(existing) > 0) {
        snprintf(cmd, sizeof(cmd), "cp %s %s", existing, host_json);
        run(cmd);
        log_info("Copied existing config to host.json");
        return 0;
    }

    /* Need to configure with OAuth code */
    char code[1024] = "";
    if (oauth_code && strlen(oauth_code) > 0) {
        strncpy(code, oauth_code, sizeof(code) - 1);
    } else {
        printf("\n");
        log_warn("No OAuth code provided. To get one:");
        printf("  1. Open a browser on this machine\n");
        printf("  2. Go to https://remotedesktop.google.com\n");
        printf("  3. Click 'Set up remote access'\n");
        printf("  4. Copy the authorization code from the URL\n\n");
        printf("Enter OAuth code (or press Enter to skip): ");
        fflush(stdout);
        if (!fgets(code, sizeof(code), stdin)) return 0;
        trim(code);
    }

    if (strlen(code) > 0) {
        log_info("Configuring Chrome Remote Desktop host...");
        const char *display = getenv("DISPLAY");
        if (!display) display = ":0";

        char start_cmd[MAX_BUF];
        snprintf(start_cmd, sizeof(start_cmd),
            "DISPLAY=%s %s/start-host --code=\"%s\" "
            "--redirect-url=\"https://remotedesktop.google.com/_/oauthredirect\" "
            "--name=%s 2>&1",
            display, CRD_INSTALL_DIR, code, getenv("HOSTNAME") ? getenv("HOSTNAME") : "linux-host");

        run(start_cmd);

        /* Copy config to expected filename */
        snprintf(ls_cmd, sizeof(ls_cmd), "ls %s/host#*.json 2>/dev/null | head -1", config_dir);
        existing[0] = '\0';
        run_capture(ls_cmd, existing, sizeof(existing));
        trim(existing);

        if (strlen(existing) > 0 && access(host_json, F_OK) != 0) {
            snprintf(cmd, sizeof(cmd), "cp %s %s", existing, host_json);
            run(cmd);
            log_info("Config saved to host.json");
        }
    } else {
        log_warn("Skipping configuration. Run again with --code=\"<your_code>\" to configure.");
    }

    return 0;
}

/* ─── Start service ────────────────────────────────────────────────── */
static int start_service(void) {
    char sudo[MAX_BUF];
    if (sudo_prefix(sudo, sizeof(sudo)) < 0) return -1;

    char cmd[MAX_BUF];
    snprintf(cmd, sizeof(cmd), "%ssystemctl enable --now crd-host", sudo);
    run(cmd);

    sleep(2);

    snprintf(cmd, sizeof(cmd), "%ssystemctl is-active --quiet crd-host", sudo);
    if (run(cmd) == 0) {
        log_info("Chrome Remote Desktop is running!");
        return 0;
    }

    log_err("Service failed to start. Check: sudo systemctl status crd-host");
    return -1;
}

/* ─── Update CRD ──────────────────────────────────────────────────── */
static int update_crd(void) {
    char installed_ver[256], remote_ver[256];

    log_info("Checking for updates...");

    get_installed_version(installed_ver, sizeof(installed_ver));
    get_remote_version(remote_ver, sizeof(remote_ver));

    printf("  Installed: %s\n", installed_ver);
    printf("  Latest:    %s\n", remote_ver);

    if (strcmp(installed_ver, "not-installed") == 0) {
        log_warn("CRD not installed. Run without --update to install first.");
        return -1;
    }

    /* Always download and reinstall (Google's URL always has latest) */
    log_info("Downloading latest Chrome Remote Desktop...");

    const char *arch_deb = detect_arch_deb();
    if (!arch_deb) { log_err("Unsupported architecture"); return -1; }

    char deb_file[] = "/tmp/crd-update-XXXXXX.deb";
    int fd = mkstemp(strdup(deb_file));
    if (fd >= 0) close(fd);

    if (download_crd(arch_deb, deb_file) != 0) {
        log_err("Download failed");
        return -1;
    }

    distro_t distro = detect_distro();
    if (install_crd(distro, deb_file) != 0) {
        log_err("Update installation failed");
        remove(deb_file);
        return -1;
    }

    /* Restart service */
    char sudo[MAX_BUF];
    if (sudo_prefix(sudo, sizeof(sudo)) < 0) return -1;
    char cmd[MAX_BUF];
    snprintf(cmd, sizeof(cmd), "%ssystemctl restart crd-host", sudo);
    run(cmd);

    remove(deb_file);
    log_info("Chrome Remote Desktop updated successfully!");
    return 0;
}

/* ─── Show status ─────────────────────────────────────────────────── */
static int show_status(void) {
    char cmd[MAX_BUF], output[MAX_BUF];
    const char *user = getenv("SUDO_USER");
    if (!user) user = getenv("USER");
    if (!user) user = "root";

    char hostname[256] = "linux-host";
    FILE *fp = fopen("/etc/hostname", "r");
    if (fp) { fgets(hostname, sizeof(hostname), fp); fclose(fp); trim(hostname); }

    char ip[64] = "unknown";
    run_capture("hostname -I 2>/dev/null | awk '{print $1}'", ip, sizeof(ip));
    trim(ip);

    char installed_ver[256];
    get_installed_version(installed_ver, sizeof(installed_ver));

    printf(CYAN "\n═══════════════════════════════════════════════════════\n" NC);
    printf(CYAN "  Chrome Remote Desktop — Status\n" NC);
    printf(CYAN "═══════════════════════════════════════════════════════\n" NC);
    printf("\n");
    printf("  Host name : %s\n", hostname);
    printf("  IP address: %s\n", ip);
    printf("  User      : %s\n", user);
    printf("  Version   : %s\n", installed_ver);
    printf("  Install   : %s\n", CRD_INSTALL_DIR);
    printf("  Service   : crd-host.service\n\n");

    /* Service status */
    snprintf(cmd, sizeof(cmd), "systemctl is-active crd-host 2>/dev/null");
    output[0] = '\0';
    run_capture(cmd, output, sizeof(output));
    trim(output);
    printf("  Status    : %s%s%s\n",
        strcmp(output, "active") == 0 ? GREEN : RED,
        strlen(output) > 0 ? output : "not-found",
        NC);

    /* Config status */
    char home[MAX_BUF];
    struct passwd *pw = getpwnam(user);
    if (pw) strncpy(home, pw->pw_dir, sizeof(home) - 1);
    else snprintf(home, sizeof(home), "/home/%s", user);

    char config_path[MAX_BUF];
    snprintf(config_path, sizeof(config_path), "%s/.config/chrome-remote-desktop/host.json", home);
    printf("  Config    : %s%s%s\n",
        access(config_path, F_OK) == 0 ? GREEN : RED,
        access(config_path, F_OK) == 0 ? "configured" : "not-configured",
        NC);

    printf("\n");
    printf("  To connect from any browser (including VR headsets):\n");
    printf("    1. Go to https://remotedesktop.google.com/access\n");
    printf("    2. Sign in with the same Google account\n");
    printf("    3. Click this machine (%s)\n", hostname);
    printf("    4. Enter the PIN you set during configuration\n\n");
    return 0;
}

/* ─── Uninstall ───────────────────────────────────────────────────── */
static int uninstall_crd(void) {
    char sudo[MAX_BUF];
    if (sudo_prefix(sudo, sizeof(sudo)) < 0) return -1;

    printf(YELLOW "\nThis will remove Chrome Remote Desktop. Continue? [y/N] " NC);
    fflush(stdout);
    char answer[16];
    if (!fgets(answer, sizeof(answer), stdin)) return 0;
    if (tolower(answer[0]) != 'y') { log_info("Uninstall cancelled"); return 0; }

    char cmd[MAX_BUF];

    /* Stop and disable service */
    snprintf(cmd, sizeof(cmd), "%ssystemctl stop crd-host 2>/dev/null", sudo); run(cmd);
    snprintf(cmd, sizeof(cmd), "%ssystemctl disable crd-host 2>/dev/null", sudo); run(cmd);
    snprintf(cmd, sizeof(cmd), "%srm -f %s", sudo, CRD_SERVICE_PATH); run(cmd);
    snprintf(cmd, sizeof(cmd), "%ssystemctl daemon-reload", sudo); run(cmd);

    /* Remove CRD files */
    snprintf(cmd, sizeof(cmd), "%srm -rf %s", sudo, CRD_INSTALL_DIR); run(cmd);

    log_info("Chrome Remote Desktop uninstalled.");
    log_warn("Config files in ~/.config/chrome-remote-desktop/ were not removed.");
    return 0;
}

/* ─── Help ────────────────────────────────────────────────────────── */
static void show_help(void) {
    printf(CYAN "\nChrome Remote Desktop Installer for Linux\n" NC);
    printf("==========================================\n\n");
    printf("Compiles to a single binary. Auto-downloads and installs the latest\n");
    printf("Chrome Remote Desktop from Google, configures it, and creates a\n");
    printf("systemd service.\n\n");
    printf(BOLD "Usage:\n" NC);
    printf("  crd-installer                    Interactive install\n");
    printf("  crd-installer --code=\"4/0AXx...\" Install with OAuth code\n");
    printf("  crd-installer --update           Update CRD to latest version\n");
    printf("  crd-installer --status           Show service status\n");
    printf("  crd-installer --uninstall        Remove CRD\n");
    printf("  crd-installer --help             Show this help\n\n");
    printf(BOLD "How to get an OAuth code:\n" NC);
    printf("  1. Open a browser on this machine\n");
    printf("  2. Go to https://remotedesktop.google.com\n");
    printf("  3. Click \"Set up remote access\"\n");
    printf("  4. Copy the authorization code from the URL\n\n");
    printf(BOLD "Supported distros:\n" NC);
    printf("  Debian, Ubuntu, Mint, Pop!_OS, Fedora, RHEL, CentOS, Rocky,\n");
    printf("  Alma, Nobara, Arch, Manjaro, EndeavourOS, openSUSE, SUSE\n\n");
    printf(BOLD "After install:\n" NC);
    printf("  - Go to remotedesktop.google.com/access from any browser\n");
    printf("  - Sign in with the same Google account\n");
    printf("  - Click this machine and enter your PIN\n\n");
}

/* ─── Main ────────────────────────────────────────────────────────── */
int main(int argc, char *argv[]) {
    char oauth_code[1024] = "";
    int do_update = 0, do_status = 0, do_uninstall = 0;

    for (int i = 1; i < argc; i++) {
        if (starts_with(argv[i], "--code=")) {
            strncpy(oauth_code, argv[i] + 7, sizeof(oauth_code) - 1);
        } else if (strcmp(argv[i], "--update") == 0) {
            do_update = 1;
        } else if (strcmp(argv[i], "--status") == 0) {
            do_status = 1;
        } else if (strcmp(argv[i], "--uninstall") == 0) {
            do_uninstall = 1;
        } else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
            show_help();
            return 0;
        } else {
            log_warn("Unknown argument. Use --help for usage.");
            return 1;
        }
    }

    printf(GREEN "\n╔════════════════════════════════════════════════════════╗\n" NC);
    printf(GREEN "║  Chrome Remote Desktop Installer — Binary Edition      ║\n" NC);
    printf(GREEN "╚════════════════════════════════════════════════════════╝\n\n" NC);

    distro_t distro = detect_distro();
    const char *arch_deb = detect_arch_deb();

    if (!arch_deb) {
        log_err("Unsupported architecture");
        return 1;
    }

    {
        char msg[256];
        snprintf(msg, sizeof(msg), "Distro: %s | Arch: %s", distro_name(distro), arch_deb);
        log_info(msg);
    }

    if (do_status)   return show_status();
    if (do_uninstall) return uninstall_crd();
    if (do_update)   return update_crd();

    /* Full install */
    log_step(1, 5, "Installing dependencies...");
    install_deps(distro);

    log_step(2, 5, "Downloading Chrome Remote Desktop...");
    char deb_file[] = "/tmp/crd-install-XXXXXX.deb";
    int fd = mkstemp(strdup(deb_file));
    if (fd >= 0) close(fd);

    if (download_crd(arch_deb, deb_file) != 0) {
        log_err("Download failed");
        return 1;
    }

    log_step(3, 5, "Installing...");
    if (install_crd(distro, deb_file) != 0) {
        log_err("Installation failed");
        remove(deb_file);
        return 1;
    }
    remove(deb_file);

    log_step(4, 5, "Configuring host...");
    configure_host(oauth_code);

    log_step(5, 5, "Creating system service...");
    create_service();
    start_service();

    show_status();
    return 0;
}
