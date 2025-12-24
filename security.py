import os

# Scan a directory for malicious content
# Checks script files for dangerous keywords
# Returns (is_malicious, reason)
def scan_for_malicious_content(directory):
    bad_keywords = [
        'rm -rf', 'sudo', 'os.system', 'subprocess', 'exec', 'eval',
        'cryptomine', 'bitcoin', 'monero', 'mining', 'forkbomb'
    ]
    for root, _, files in os.walk(directory):
        for file in files:
            if file.endswith(('.py', '.sh', '.bash')):  # Focus on scripts
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read().lower()
                        for kw in bad_keywords:
                            if kw in content:
                                return True, f"Malicious keyword '{kw}' found in {file}"
                except Exception as e:
                    return True, f"Error reading file {file}: {str(e)}"
    return False, ""
