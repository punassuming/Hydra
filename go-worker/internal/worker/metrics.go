package worker

import (
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
)

// collectMetrics gathers process-level metrics from /proc (Linux) or
// runtime stats (other OS). Returns a map suitable for JSON serialization.
func collectMetrics() map[string]interface{} {
	if runtime.GOOS == "linux" {
		return collectLinuxMetrics()
	}
	// Fallback: use Go runtime stats.
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	return map[string]interface{}{
		"process_count": 1,
		"memory_rss_mb": float64(m.Sys) / (1024 * 1024),
	}
}

// collectLinuxMetrics mirrors the Python _collect_process_metrics():
// sum VmRSS across /proc entries and read /proc/loadavg.
func collectLinuxMetrics() map[string]interface{} {
	totalRSSKB := 0
	processCount := 0

	entries, err := os.ReadDir("/proc")
	if err == nil {
		for _, entry := range entries {
			name := entry.Name()
			if !isNumeric(name) {
				continue
			}
			rss := readVmRSS(filepath.Join("/proc", name, "status"))
			if rss >= 0 {
				processCount++
				totalRSSKB += rss
			}
		}
	}

	result := map[string]interface{}{
		"process_count": processCount,
		"memory_rss_mb": float64(totalRSSKB) / 1024.0,
	}

	// Read load averages from /proc/loadavg.
	data, err := os.ReadFile("/proc/loadavg")
	if err == nil {
		parts := strings.Fields(string(data))
		if len(parts) >= 2 {
			if v, err := strconv.ParseFloat(parts[0], 64); err == nil {
				result["load_1m"] = v
			}
			if v, err := strconv.ParseFloat(parts[1], 64); err == nil {
				result["load_5m"] = v
			}
		}
	}
	return result
}

// readVmRSS reads VmRSS from a /proc/[pid]/status file. Returns KB or -1.
func readVmRSS(path string) int {
	data, err := os.ReadFile(path)
	if err != nil {
		return -1
	}
	for _, line := range strings.Split(string(data), "\n") {
		if strings.HasPrefix(line, "VmRSS:") {
			fields := strings.Fields(line)
			if len(fields) >= 2 {
				v, err := strconv.Atoi(fields[1])
				if err == nil {
					return v
				}
			}
			break
		}
	}
	return -1
}

func isNumeric(s string) bool {
	for _, c := range s {
		if c < '0' || c > '9' {
			return false
		}
	}
	return len(s) > 0
}
