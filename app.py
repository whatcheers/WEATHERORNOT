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
from mappings import map_nws_product_to_hass_severity, map_nws_product_code_to_description
import paho.mqtt.client as mqtt

# These lines are so Flask shuts the fuck up in the console so I can see wtf is happening
import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.WARNING)


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
mqttclient = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

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

colorL = "\033[96m" #color for console messages related to leftchat
colorR = "\033[94m" #color for console messages related to rightchat
reset_color = '\033[0m'  # resets color to default
ul_start = '\033[4m'  # Start underline
ul_end = '\033[24m'  # End underline
bold_start = '\033[1m'  # Start bold
bold_end = '\033[22m'  # End bold

def generate_timestamp_for_console():
    # time_color = '\033[0;30;47m'  # black on white
    time_color = '\033[90m' # dark gray
    current_time = datetime.now().strftime('%H:%M:%S')
    colored_timestamp = f"{time_color}[{current_time}]{reset_color}"
    return colored_timestamp

def generate_LR_coloring_for_console(feed_name):
    formatted_feed_name = f"[{feed_name[0].upper()} SIDE]"
    if feed_name[0].upper() == "R":
        color_to_use = colorR
    else:
        color_to_use = colorL
    return color_to_use + formatted_feed_name

def format_description(description):
    return description.replace('<pre>', '<pre style="white-space: pre-wrap;">')

def fetch_and_update_feed(feed_name, url):
    while True:
        try:
            print(f"{generate_timestamp_for_console()} {generate_LR_coloring_for_console(feed_name)} [Getting] {url}{reset_color}")
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
                payload_for_mqtt = format_payload_for_mqtt(first_item, feed_name)
                print(f"{generate_timestamp_for_console()} {generate_LR_coloring_for_console(feed_name)} [Publish] mqtt://{mqtt_broker}:{mqtt_port}{reset_color}")
                if feed_name == 'leftchat':
                    send_to_hass_mqtt(mqtt_topicleft, payload_for_mqtt)
                else:
                    send_to_hass_mqtt(mqtt_topicright, payload_for_mqtt)
        except requests.RequestException as e:
            print(f"{generate_timestamp_for_console()}\033[31m Error fetching the feed {feed_name}: {e}{reset_color}")
        except ET.ParseError as e:
            print(f"{generate_timestamp_for_console()}\033[31m Error parsing the XML {feed_name}: {e}{reset_color}")
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
    print(f"{generate_timestamp_for_console()} Updated interval to {INTERVAL} seconds")

def format_payload_for_mqtt(json_data, feed_name):
    json_text = json.dumps(json_data)
    # Parse the JSON text into a Python dictionary
    parsed_json = json.loads(json_text)
    # Access the parsed data
    json_found_title = parsed_json['title']
    json_found_description = parsed_json['description']
    json_found_pubdate = parsed_json['pub_date']
    json_found_link = parsed_json['link']
    # parse the description for severity
    severity = identify_nws_product_severity(json_found_description, feed_name)
    # clean up the description
    mqtt_description = json_found_description
    mqtt_description_lines = mqtt_description.split('\n')
    if len(mqtt_description_lines) >= 4:
        mqtt_description = '\n'.join(mqtt_description_lines[3:])
        mqtt_section_title = mqtt_description_lines[3]
        if mqtt_section_title == '' and len(mqtt_description_lines) >= 5:
            mqtt_section_title = mqtt_description_lines[4]
        else:
            mqtt_section_title = 'Details'
    mqtt_description = mqtt_description.replace('<pre style="white-space: pre-wrap;">','').replace('</pre>','')
    mqtt_description = mqtt_description.replace('\n', '<br>') # change newline format, it's easier to deal with
    mqtt_description = mqtt_description.replace('\'','\'\'') # escape single quotes for MQTT by changing ' to ''
    mqtt_description = mqtt_description.strip()
    # format a payload that Home Assistant's Markdown card will render. Using syntax here: https://www.home-assistant.io/dashboards/markdown/#ha-alert
    mqtt_payload = "<ha-alert alert-type=\"" + severity + "\" title=\"" + json_found_title.replace("\"", "&quot;") + "\"></ha-alert><details><summary>" + mqtt_section_title + "</summary>" + mqtt_description + "</details>"
    mqtt_payload = mqtt_payload.replace('"','\\\"')
    #mqtt_payload = mqtt_payload.replace('$$','')
    return mqtt_payload

def identify_nws_product_severity(nws_product_description, feed_name):
    # NWS products have the product code as the third line, first three characters
    lines = nws_product_description.split('\n')
    if len(lines) >= 3:
        third_line_first_three_chars = lines[2][:3] # second index is third line, grab first three characters
        third_line_second_three_characters = lines[2][3:6] # second index is third line, grab second three characters
        severity_from_dictionary = map_nws_product_to_hass_severity.get(third_line_first_three_chars, None)
        description_from_dictionary = map_nws_product_code_to_description.get(third_line_first_three_chars, None)

        print(f"{generate_timestamp_for_console()} {generate_LR_coloring_for_console(feed_name)} [Payload] Office: \"{ul_start}{third_line_second_three_characters}{ul_end}\" Prod: \"{ul_start}{third_line_first_three_chars}{ul_end}\" Desc: \"{ul_start}{description_from_dictionary}{ul_end}\" Sev: \"{ul_start}{severity_from_dictionary}{ul_end}\"{reset_color}")
    else:
        severity_from_dictionary = "info"

        nws_office_color = "\033[31m" #red
        product_code_color = "\033[31m" #red
        description_color = "\033[31m" #red
        severity_color = "\033[31m" #red
        print(f"{generate_timestamp_for_console()} {generate_LR_coloring_for_console(feed_name)} [Payload] Office: \"{ul_start}{third_line_second_three_characters}{ul_end}\" Prod: \"{ul_start}{third_line_first_three_chars}{ul_end}\" Desc: \"{ul_start}NOT IN DICTIONARY{ul_end}\" Sev: \"{ul_start}info (assumed){ul_end}\"{reset_color}")
    return severity_from_dictionary

def send_to_hass_mqtt(topic, text):
    mqttclient = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    mqttclient.username_pw_set(mqtt_user, mqtt_pass)

    def on_connect(mqttclient, userdata, flags, rc):
        mqttclient.publish(topic, '{"payload":"' + text + '"}')
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
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
