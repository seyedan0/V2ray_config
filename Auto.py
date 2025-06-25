import requests
import socket
import time
from urllib.parse import urlparse, parse_qs
import base64
import json
import subprocess
import os

DEFAULT_SUB_URL = 'https://raw.githubusercontent.com/Epodonios/v2ray-configs/refs/heads/main/Sub25.txt'
DEFAULT_OUTPUT_FILE = 'filtered_nodes.txt'

MAX_DELAY_MS = 1500
XRAY_PATH = './xray.exe' if os.name == 'nt' else './xray'
LOCAL_SOCKS_PORT = 10808
REAL_DELAY_URL = 'http://www.gstatic.com/generate_204'
XRAY_CONFIG_FILE = 'temp_config.json'


def base64_decode(data):
    data += '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data.encode()).decode('utf-8')

def get_config_from_link(link):
    if link.startswith("vmess://"):
        try:
            decoded_json = base64_decode(link[len("vmess://"):])
            return json.loads(decoded_json)
        except Exception:
            return None
    elif link.startswith(("vless://", "trojan://")):
        try:
            parsed = urlparse(link)
            config = {
                'add': parsed.hostname,
                'port': parsed.port,
                'id': parsed.username,
                'protocol': parsed.scheme
            }
            params = parse_qs(parsed.query)
            if 'security' in params: config['security'] = params['security'][0]
            if 'type' in params: config['net'] = params['type'][0]
            if 'path' in params: config['path'] = params['path'][0]
            if 'host' in params: config['host'] = params['host'][0]
            if 'sni' in params: config['sni'] = params['sni'][0]
            return config
        except Exception:
            return None
    return None

def create_xray_config(node_config):
    protocol = node_config.get('protocol', 'vmess')
    outbound_settings = {
        'vnext': [{
            'address': node_config.get('add'),
            'port': int(node_config.get('port')),
            'users': [{'id': node_config.get('id')}]
        }]
    }
    if protocol == 'trojan':
        outbound_settings = {
            'servers': [{
                'address': node_config.get('add'),
                'port': int(node_config.get('port')),
                'password': node_config.get('id')
            }]
        }
    stream_settings = {
        'network': node_config.get('net', 'tcp'),
        'security': node_config.get('security', 'none')
    }
    if stream_settings['security'] == 'tls':
        stream_settings['tlsSettings'] = {'serverName': node_config.get('host') or node_config.get('sni') or node_config.get('add')}
    if stream_settings['network'] == 'ws':
        stream_settings['wsSettings'] = {'path': node_config.get('path', '/'), 'headers': {'Host': node_config.get('host', node_config.get('add'))}}
    config = {
        "inbounds": [{"port": LOCAL_SOCKS_PORT, "listen": "127.0.0.1", "protocol": "socks", "settings": {"auth": "noauth", "udp": True}}],
        "outbounds": [{"protocol": protocol, "settings": outbound_settings, "streamSettings": stream_settings}]
    }
    try:
        with open(XRAY_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error creating config file: {e}")
        return False

def test_real_delay(timeout_sec=5):
    process = None
    try:
        process = subprocess.Popen([XRAY_PATH, "run", "-c", XRAY_CONFIG_FILE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        proxies = {
            'http': f'socks5h://127.0.0.1:{LOCAL_SOCKS_PORT}',
            'https': f'socks5h://127.0.0.1:{LOCAL_SOCKS_PORT}'
        }
        start_time = time.time()
        response = requests.get(REAL_DELAY_URL, proxies=proxies, timeout=timeout_sec)
        end_time = time.time()
        if response.status_code == 204:
            return int((end_time - start_time) * 1000)
        else:
            return None
    except requests.exceptions.RequestException:
        return None
    finally:
        if process:
            process.terminate()
            process.wait()
        if os.path.exists(XRAY_CONFIG_FILE):
            os.remove(XRAY_CONFIG_FILE)

def git_push(filename, commit_message="Update filtered nodes"):
    try:
        status_result = subprocess.run(["git", "status", "--porcelain"], check=True, capture_output=True, text=True)
        if not status_result.stdout.strip():
            print("ℹ️ No changes to commit.")
            return

        print(f"✈️ Pushing {filename} to Git repository...")
        subprocess.run(["git", "add", filename], check=True)
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Pushed changes successfully.")
    except FileNotFoundError:
        print("❌ Git command not found. Make sure Git is installed and in your PATH.")
    except subprocess.CalledProcessError as e:
        if "nothing to commit" in e.stderr.lower():
             print("ℹ️ No changes to commit.")
        else:
            print(f"❌ Git error: {e.stderr}")

def main():
    print("--- script option ---")
    user_sub_url = input(f"sub link: {DEFAULT_SUB_URL}): ")
    user_output_file = input(f"out put file: {DEFAULT_OUTPUT_FILE}): ")
    
    sub_url = user_sub_url if user_sub_url else DEFAULT_SUB_URL
    output_file = user_output_file if user_output_file else DEFAULT_OUTPUT_FILE
    
    print("\n🚀 Script started for Real Delay Test")
    print(f" Subscription URL: {sub_url}")
    print(f" Output File: {output_file}\n")
    
    if not os.path.exists(XRAY_PATH):
        print(f"❌ Error: Xray executable not found at '{XRAY_PATH}'. Please download it and place it here.")
        return
        
    try:
        res = requests.get(sub_url)
        res.raise_for_status()
        raw = res.text.strip()
        print("✅ Subscription downloaded")
    except Exception as e:
        print(f"❌ Error fetching subscription: {e}")
        return

    nodes = [line.strip() for line in raw.splitlines() if line.startswith(('vmess://', 'vless://', 'trojan://'))]
    print(f"📦 Found {len(nodes)} total nodes")

    filtered_nodes = []
    for i, link in enumerate(nodes, 1):
        print(f"[{i}/{len(nodes)}] ", end='')
        config = get_config_from_link(link)
        if not config:
            print(f"⚠️ Skipped: Can't parse {link[:40]}...")
            continue
        
        if not create_xray_config(config):
            print(f"⚠️ Skipped: Failed to create config for {config.get('add')}")
            continue

        print(f"⏳ Testing {config.get('add')}:{config.get('port')}...", end=' ')
        delay = test_real_delay()
        
        if delay is not None and delay < MAX_DELAY_MS:
            print(f"✅ Real Delay: {delay} ms")
            filtered_nodes.append(link)
        elif delay is None:
            print("❌ Timeout or connection error")
        else:
            print(f"❌ Too slow: {delay} ms")

    if filtered_nodes:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(filtered_nodes))
        print(f"\n🎉 Exported {len(filtered_nodes)} fast nodes to {output_file}")
        
        git_push(output_file, f"Update nodes: {len(filtered_nodes)} fast nodes found")
        
    else:
        print(f"\n⚠️ No fast nodes under {MAX_DELAY_MS}ms found.")

if __name__ == '__main__':
    main()