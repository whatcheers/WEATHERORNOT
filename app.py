from flask import Flask, render_template, request, jsonify, make_response
from flask_socketio import SocketIO
from datetime import datetime, timezone
import requests
import xml.etree.ElementTree as ET
import threading
import time
import sys
import configparser
import json
import re
from mappings import map_nws_product_to_hass_severity
import paho.mqtt.client as mqtt

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

config = configparser.ConfigParser()
config.read('secrets.ini')

# Retrieve MQTT config from secrets.ini
mqtt_broker = config['MQTT']['broker']
mqtt_port = int(config['MQTT']['port']) # Force to integer
mqtt_user = config['MQTT']['user']
mqtt_pass = config['MQTT']['pass']
mqtt_topicleft = config['MQTT']['topicleft']
mqtt_topicright = config['MQTT']['topicright']
# Create an MQTT client instance
mqttclient = mqtt.Client()

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
            if items and items[:10]:
                first_item = items[:10][0]
                payload_for_mqtt = format_payload_for_mqtt(first_item)
                send_to_hass_mqtt(mqtt_topicleft, payload_for_mqtt)
                #send_to_hass_mqtt(mqtt_topicleft,'<ha-alert alert-type=\\"info\\" title=\\"this\\">1\\n4</ha-alert>')
                send_to_hass_mqtt(mqtt_topicright, 'derp')
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
    #mode = request.cookies.get('mode', 'light')  # Default to light mode if no cookie is set
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

@app.route('/set_mode/<mode>')
def set_mode(mode):
    if mode in ['light', 'dark']:
        resp = make_response('Mode set to ' + mode)
        resp.set_cookie('mode', mode, max_age=30*24*60*60)  # Cookie lasts for 30 days
        return resp
    return 'Invalid mode', 400

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

def format_payload_for_mqtt(json_data):
    json_text = json.dumps(json_data)
    # Parse the JSON text into a Python dictionary
    parsed_json = json.loads(json_text)
    # Access the parsed data
    json_found_title = parsed_json['title']
    json_found_description = parsed_json['description']
    json_found_pubdate = parsed_json['pub_date']
    json_found_link = parsed_json['link']
    # parse the title for severity
    match = re.search(r'\((.*?)\)', json_found_title)
    if match:
        code_in_parenthesis = match.group(1)
        severity_based_on_nws_product = map_nws_product_to_hass_severity.get(code_in_parenthesis, None)
        if severity_based_on_nws_product:
            severity = severity_based_on_nws_product # we found the severity
        else:
            severity = "info" # we had a parenthetical code in the json title but it didn't match mapping dictionary
    else:
        severity = "info" # there was no code in parenthesis in the json title so regex didn't match
    # clean up the description
    mqtt_description = json_found_description
    mqtt_description = mqtt_description.replace('\n', '<br>') # change newline format, it's easier to deal with
    mqtt_description = mqtt_description.replace('<pre style="white-space: pre-wrap;">','')
    mqtt_description = mqtt_description.replace('</pre>','')
    mqtt_description = mqtt_description.replace('\'','\'\'') # escape single quotes for MQTT by changing ' to ''
    mqtt_description = mqtt_description.strip()
    mqtt_payload = "<ha-alert alert-type=\"" + severity + "\" title=\"" + json_found_title + "\">" + mqtt_description + "</ha-alert>"
    mqtt_payload = mqtt_payload.replace('"','\\\"')
    #mqtt_payload = mqtt_payload.replace('$$','')
    return mqtt_payload

def send_to_hass_mqtt(topic, text):
    mqttclient = mqtt.Client()
    mqttclient.username_pw_set(mqtt_user, mqtt_pass)

    def on_connect(mqttclient, userdata, flags, rc):
        print(f"Connected to MQTT with result code {rc}")
        mqttclient.publish(topic, '{"payload":"' + text + '"}')
        #print(f"Published to MQTT - {topic}: {text}")
        mqttclient.disconnect()

    mqttclient.on_connect = on_connect
    mqttclient.connect(mqtt_broker, mqtt_port, 60)
    mqttclient.loop_start()
    time.sleep(2)
    mqttclient.loop_stop()

if __name__ == '__main__':
    for feed_name, url in FEED_URLS.items():
        thread = threading.Thread(target=fetch_and_update_feed, args=(feed_name, url))
        thread.daemon = True
        thread.start()
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
