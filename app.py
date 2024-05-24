from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import requests
import xml.etree.ElementTree as ET
import threading
import time
from datetime import datetime, timezone
import sys

# Check if both command-line arguments are provided
if len(sys.argv) != 3:
    print("")
    print("ERROR: You need to pass two IEMBOT ids as parameters")
    print("")
    print("     Example: 'python app.py dvn tbw'")
    print("")
    print("     Result: Davenport IEMBOT on left side, Tampa IEMBOT on the right")
    print("")
    print("You can find a list of valid IEMBOT ids at https://weather.im/iembot/")
    sys.exit(1)

# Extract IEMBOT ids from command-line arguments
leftchat = sys.argv[1]
rightchat = sys.argv[2]

# Define the base URLs
BASE_URL = 'https://weather.im/iembot-rss/room/'

# Construct the feed URLs
leftchat_url = f"{BASE_URL}{leftchat}chat.xml"
rightchat_url = f"{BASE_URL}{rightchat}chat.xml"

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

# Set the UTC timezone explicitly
utc_timezone = timezone.utc

FEED_URLS = {
    'leftchat': leftchat_url,
    'rightchat': rightchat_url
}
INTERVAL = 60  # Fetch interval in seconds

data_store = {
    'leftchat': {'items': [], 'last_update_time': None},
    'rightchat': {'items': [], 'last_update_time': None}
}

def format_description(description):
    return description.replace('<pre>', '<pre style="white-space: pre-wrap;">')

def fetch_and_update_feed(feed_name, url):
    while True:
        try:
            print('\033[92mGETTING UPDATE FROM: ' + url + '\033[0m')
            response = requests.get(url)
            response.raise_for_status()
            xml_data = response.content
            root = ET.fromstring(xml_data)
            items = []
            for item in root.findall('.//item'):
                title = item.find('title').text
                description = item.find('description').text
                pub_date = item.find('pubDate').text
                link = item.find('link').text
                items.append({
                    'title': title,
                    'description': format_description(description),
                    'pub_date': pub_date,
                    'link': link
                })
            data_store[feed_name]['items'] = items
            data_store[feed_name]['last_update_time'] = datetime.utcnow().isoformat() + 'Z'
            #data_store[feed_name]['last_update_time'] = datetime.now(timezone.utc).isoformat(timespec='seconds') + 'Z'
            socketio.emit(f'update_feed_{feed_name}', {
                'items': items[:10],
                'last_update_time': data_store[feed_name]['last_update_time']
            })
        except requests.RequestException as e:
            print(f'Error fetching the feed {feed_name}: {e}')
        except ET.ParseError as e:
            print(f'Error parsing the XML {feed_name}: {e}')
        time.sleep(INTERVAL)

def fetch_cow_stats(wfo=None, phenomena=None, callback=None):
    base_url = 'https://mesonet.agron.iastate.edu/api/1/cow.json'
    params = {
        'wfo': wfo,
        'phenomena': phenomena,
        'callback': callback
    }
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()  # Raises an exception for 4XX/5XX responses
        return response.json()
    except requests.RequestException as e:
        return {'error': str(e)}

@socketio.on('request_cow_stats')
def handle_request_cow_stats(data):
    wfo = data.get('wfo')
    phenomena = data.get('phenomena')
    callback = data.get('callback')
    stats = fetch_cow_stats(wfo=wfo, phenomena=phenomena, callback=callback)
    socketio.emit('cow_stats_response', stats)

@app.route('/')
def index():
    leftchatname = leftchat.upper()
    rightchatname = rightchat.upper()
    return render_template('index.html', leftchatname=leftchatname, rightchatname=rightchatname)

@app.route('/feed/<feed_name>', methods=['GET'])
def get_feed(feed_name):
    page = int(request.args.get('page', 1))
    per_page = 10
    start = (page - 1) * per_page
    end = start + per_page
    items = data_store.get(feed_name, {}).get('items', [])
    last_update_time = data_store.get(feed_name, {}).get('last_update_time', None)
    return jsonify({
        'items': items[start:end],
        'total': len(items),
        'last_update_time': last_update_time
    })

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    for feed_name in FEED_URLS:
        items = data_store.get(feed_name, {}).get('items', [])
        last_update_time = data_store.get(feed_name, {}).get('last_update_time', None)
        socketio.emit(f'update_feed_{feed_name}', {
            'items': items[:10],
            'last_update_time': last_update_time
        })

@socketio.on('update_interval')
def handle_update_interval(data):
    global INTERVAL
    INTERVAL = int(data['interval'])
    print(f"Updated interval to {INTERVAL} seconds")

if __name__ == '__main__':
    for feed_name, url in FEED_URLS.items():
        thread = threading.Thread(target=fetch_and_update_feed, args=(feed_name, url))
        thread.daemon = True
        thread.start()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
