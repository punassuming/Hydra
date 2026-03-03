// Package source implements source provisioning (git, copy, rsync) for the
// Go worker, mirroring the Python worker's utils/git.py, utils/copy.py,
// and utils/rsync.py.
package source

import (
	"fmt"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// FetchGit clones a git repository to dest, checking out ref.
// token is injected into HTTPS URLs for private repository auth.
// When sparsePath is non-empty, a sparse-checkout is used.
func FetchGit(repoURL, ref, dest, token, sparsePath string) error {
	cloneURL := repoURL
	if token != "" {
		cloneURL = injectToken(repoURL, token)
	}
	if sparsePath != "" {
		return sparseClone(cloneURL, ref, dest, sparsePath)
	}
	return fullClone(cloneURL, ref, dest)
}

func fullClone(cloneURL, ref, dest string) error {
	// Try shallow clone first.
	cmd := exec.Command("git", "clone", "-q", "--depth", "1", cloneURL, dest)
	if err := cmd.Run(); err != nil {
		// Fall back to full clone.
		os.RemoveAll(dest)
		os.MkdirAll(dest, 0755)
		cmd = exec.Command("git", "clone", "-q", cloneURL, dest)
		if out, err := cmd.CombinedOutput(); err != nil {
			return fmt.Errorf("git clone failed: %s", string(out))
		}
	}
	if ref != "" {
		cmd = exec.Command("git", "checkout", ref)
		cmd.Dir = dest
		if out, err := cmd.CombinedOutput(); err != nil {
			return fmt.Errorf("git checkout %s failed: %s", ref, string(out))
		}
	}
	return nil
}

func sparseClone(cloneURL, ref, dest, sparsePath string) error {
	os.MkdirAll(dest, 0755)
	run := func(args ...string) error {
		cmd := exec.Command(args[0], args[1:]...)
		cmd.Dir = dest
		if out, err := cmd.CombinedOutput(); err != nil {
			return fmt.Errorf("%s failed: %s", args[0], string(out))
		}
		return nil
	}
	if err := run("git", "init", "-q", dest); err != nil {
		return err
	}
	if err := run("git", "remote", "add", "origin", cloneURL); err != nil {
		return err
	}
	if err := run("git", "sparse-checkout", "set", "--cone", sparsePath); err != nil {
		return err
	}
	fetchRef := ref
	if fetchRef == "" {
		fetchRef = "HEAD"
	}
	// Try shallow fetch first.
	cmd := exec.Command("git", "fetch", "-q", "--depth", "1", "origin", fetchRef)
	cmd.Dir = dest
	if err := cmd.Run(); err != nil {
		if err := run("git", "fetch", "-q", "origin", fetchRef); err != nil {
			return err
		}
	}
	checkoutRef := ref
	if checkoutRef == "" {
		checkoutRef = "FETCH_HEAD"
	}
	return run("git", "checkout", checkoutRef)
}

func injectToken(rawURL, token string) string {
	u, err := url.Parse(rawURL)
	if err != nil {
		return rawURL
	}
	if u.Scheme != "http" && u.Scheme != "https" {
		return rawURL
	}
	host := u.Hostname()
	if u.Port() != "" {
		host = host + ":" + u.Port()
	}
	u.User = url.UserPassword("x-oauth-token", token)
	return u.String()
}

// FetchCopy copies a local file or directory to dest.
func FetchCopy(src, dest string) error {
	if !filepath.IsAbs(src) {
		return fmt.Errorf("copy source path must be absolute, got: %s", src)
	}
	info, err := os.Stat(src)
	if err != nil {
		return fmt.Errorf("copy source path not found: %s", src)
	}
	if info.IsDir() {
		return copyDir(src, dest)
	}
	return copyFile(src, filepath.Join(dest, filepath.Base(src)))
}

// FetchRsync fetches files from a remote host via rsync over SSH.
func FetchRsync(srcURL, dest, sshKeyPath string) error {
	args := []string{"rsync", "-az", "--delete"}
	if sshKeyPath != "" {
		args = append(args, "-e", fmt.Sprintf("ssh -i %s -o StrictHostKeyChecking=no", sshKeyPath))
	}
	srcURL = strings.TrimRight(srcURL, "/") + "/"
	dest = strings.TrimRight(dest, "/") + "/"
	args = append(args, srcURL, dest)

	cmd := exec.Command(args[0], args[1:]...)
	if out, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("rsync failed: %s", string(out))
	}
	return nil
}

// ---------------------------------------------------------------------------
// File copy helpers
// ---------------------------------------------------------------------------

func copyDir(src, dst string) error {
	return filepath.Walk(src, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(src, path)
		target := filepath.Join(dst, rel)
		if info.IsDir() {
			return os.MkdirAll(target, info.Mode())
		}
		return copyFile(path, target)
	})
}

func copyFile(src, dst string) error {
	os.MkdirAll(filepath.Dir(dst), 0755)
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0644)
}
