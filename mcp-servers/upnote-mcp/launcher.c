/*
 * Starts the UpNote MCP server so a Full Disk Access grant survives upgrades.
 *
 * The Claude desktop app launches MCP servers as their own "responsible" process, so macOS
 * checks the launched binary, not Claude, before letting it read UpNote's
 * container. Homebrew's uv and Python are ad-hoc signed, so a grant on them is
 * tied to one exact build and is lost on every brew upgrade. This launcher
 * never changes, so a grant on it holds. It must stay alive as the parent:
 * exec'ing the interpreter would make it the binary macOS checks again.
 *
 * uv is not in the chain at all. Even with this launcher as the parent, macOS
 * recorded an "access data from UpNote" decision against each Homebrew uv build
 * (2026-10-09), locked to Off, and every uv upgrade added another. The server
 * runs instead on a venv built from python.org's Python, which is signed by the
 * Python Software Foundation and which Homebrew never touches.
 *
 * It takes no arguments, so its command line cannot point the grant at another
 * program. Both paths are built from $HOME at startup, though, so anyone who
 * can set HOME for it can run their own code under the grant.
 *
 * Build: see README.md, "Install".
 */
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>

/* Relative to $HOME. Built per README.md, "Install". */
#define VENV_PYTHON "/.claude/mcp-servers/upnote-mcp-venv/bin/python"

extern char **environ;

static pid_t child;

static void forward(int sig) {
    if (child > 0)
        kill(child, sig);
}

int main(void) {
    const char *home = getenv("HOME");
    if (!home) {
        fprintf(stderr, "upnote-mcp-launcher: HOME is not set\n");
        return 1;
    }
    char python[4096], script[4096];
    snprintf(python, sizeof python, "%s%s", home, VENV_PYTHON);
    snprintf(script, sizeof script, "%s/.claude/mcp-servers/upnote-mcp/server.py", home);

    /* -I: no PYTHON* variables, no user site-packages, so only the venv runs. */
    char *args[] = {python, "-I", script, NULL};
    int err = posix_spawn(&child, python, NULL, NULL, args, environ);
    if (err) {
        fprintf(stderr, "upnote-mcp-launcher: cannot start %s: %s\n", python, strerror(err));
        return 1;
    }

    signal(SIGTERM, forward);
    signal(SIGINT, forward);
    signal(SIGHUP, forward);

    int status;
    while (waitpid(child, &status, 0) < 0) {
    }
    if (WIFEXITED(status))
        return WEXITSTATUS(status);
    return 128 + WTERMSIG(status);
}
