from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import sys
import logging
import time
import getopt
from datetime import datetime
import picamera
import os
import tinys3
import json
from smartcard.System import readers
from smartcard.util import toHexString
from smartcard.ATR import ATR
from smartcard.CardType import AnyCardType
import boto
import boto.s3
import sys
from boto.s3.key import Key
import RPi.GPIO as GPIO
import lcddriver
import datetime

#servo definisi
servoPIN = 17
GPIO.setmode(GPIO.BCM)
GPIO.setup(servoPIN, GPIO.OUT)
p = GPIO.PWM(servoPIN, 50) # GPIO 17 for PWM with 50Hz
p.start(2.5) # Initialization

#display i2c
display = lcddriver.lcd()


AWS_ACCESS_KEY_ID = 'AKIAJHZ53O3OQALEAZLQ'
AWS_SECRET_ACCESS_KEY = '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'

# Usage
usageInfo = """Usage:
Use certificate based mutual authentication:
python rpi_rfid_rekognition.py -e <endpoint> -r <rootCAFilePath> -c <certFilePath> -k <privateKeyFilePath>
Type "python rpi_rfid_rekognition.py -h" for available options.
"""
# Help info
helpInfo = """-e, --endpoint
	Your AWS IoT custom endpoint
-r, --rootCA
	Root CA file path
-c, --cert
	Certificate file path
-k, --key
	Private key file path
-h, --help
	Help information
"""

# Read in command-line parameters
host = 'a1nm0zbf5a0ay7-ats.iot.ap-southeast-1.amazonaws.com'
rootCAPath = 'Raspi_IOT/root-CA.crt'
certificatePath = 'Raspi_IOT/Raspi_IOT.cert.pem'
privateKeyPath = 'Raspi_IOT/Raspi_IOT.private.key'
try:
	opts, args = getopt.getopt(sys.argv[1:], "hwe:k:c:r:", ["help", "endpoint=", "key=","cert=","rootCA="])
	if len(opts) == 0:
		raise getopt.GetoptError("No input parameters!")
	for opt, arg in opts:
		if opt in ("-h", "--help"):
			print(helpInfo)
			exit(0)
		if opt in ("-e", "--endpoint"):
			host = arg
		if opt in ("-r", "--rootCA"):
			rootCAPath = arg
		if opt in ("-c", "--cert"):
			certificatePath = arg
		if opt in ("-k", "--key"):
			privateKeyPath = arg
except getopt.GetoptError:
	print(usageInfo)
	exit(1)

# Missing configuration notification
missingConfiguration = False
if not host:
	print("Missing '-e' or '--endpoint'")
	missingConfiguration = True
if not rootCAPath:
	print("Missing '-r' or '--rootCA'")
	missingConfiguration = True
if not certificatePath:
    print("Missing '-c' or '--cert'")
    missingConfiguration = True
if not privateKeyPath:
    print("Missing '-k' or '--key'")
    missingConfiguration = True
if missingConfiguration:
	exit(2)

# photo properties
image_width = 800
image_height = 600
file_extension = '.jpg'

# AWS S3 properties
access_key_id = 'AKIAJHZ53O3OQALEAZLQ'
secret_access_key = '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'
bucket_name = 'iot-digitalent'

# RFID character map for hid device
hid = { 4: 'a', 5: 'b', 6: 'c', 7: 'd', 8: 'e', 9: 'f', 10: 'g', 11: 'h', 12: 'i', 13: 'j', 14: 'k', 15: 'l', 16: 'm', 17: 'n', 18: 'o', 19: 'p', 20: 'q', 21: 'r', 22: 's', 23: 't', 24: 'u', 25: 'v', 26: 'w', 27: 'x', 28: 'y', 29: 'z', 30: '1', 31: '2', 32: '3', 33: '4', 34: '5', 35: '6', 36: '7', 37: '8', 38: '9', 39: '0', 44: ' ', 45: '-', 46: '=', 47: '[', 48: ']', 49: '\\', 51: ';' , 52: '\'', 53: '~', 54: ',', 55: '.', 56: '/'  }
hid2 = { 4: 'A', 5: 'B', 6: 'C', 7: 'D', 8: 'E', 9: 'F', 10: 'G', 11: 'H', 12: 'I', 13: 'J', 14: 'K', 15: 'L', 16: 'M', 17: 'N', 18: 'O', 19: 'P', 20: 'Q', 21: 'R', 22: 'S', 23: 'T', 24: 'U', 25: 'V', 26: 'W', 27: 'X', 28: 'Y', 29: 'Z', 30: '!', 31: '@', 32: '#', 33: '$', 34: '%', 35: '^', 36: '&', 37: '*', 38: '(', 39: ')', 44: ' ', 45: '_', 46: '+', 47: '{', 48: '}', 49: '|', 51: ':' , 52: '"', 53: '~', 54: '<', 55: '>', 56: '?'  }

# Configure logging
logger = logging.getLogger("AWSIoTPythonSDK.core")
logger.setLevel(logging.DEBUG)
streamHandler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
streamHandler.setFormatter(formatter)
logger.addHandler(streamHandler)

# Init AWSIoTMQTTClient
myAWSIoTMQTTClient = None

myAWSIoTMQTTClient = AWSIoTMQTTClient("basicPubSub")
myAWSIoTMQTTClient.configureEndpoint(host, 8883)
myAWSIoTMQTTClient.configureCredentials(rootCAPath, privateKeyPath, certificatePath)

# AWSIoTMQTTClient connection configuration
myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
myAWSIoTMQTTClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
myAWSIoTMQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
myAWSIoTMQTTClient.configureConnectDisconnectTimeout(10)  # 10 sec
myAWSIoTMQTTClient.configureMQTTOperationTimeout(5)  # 5 sec

# camera setup
camera = picamera.PiCamera()
camera.resolution = (image_width, image_height)
camera.awb_mode = 'auto'

# Start listening on RFID events
r = readers()
if len(r) < 1:
    print "error: No readers available!"
    sys.exit()

print "Available readers: ", r

reader = r[0]
print "Using: ", reader

def scanRFID():
    ss = ""
    done = False

    while not done:
        try:
            connection = reader.createConnection()
            connection.connect()

            data, sw1, sw2 = connection.transmit([0xFF, 0xCA, 0x00, 0x00, 0x00])
            #print "ID: " + toHexString(data)
            #if (sw1, sw2) == (0x90, 0x0):
                #print "Status: The operation completed successfully."
            #elif (sw1, sw2) == (0x63, 0x0):
            #   print "Status: The operation failed."
            ss = toHexString(data)          
                        
            done = True
            
        except Exception,e: 
            #print str(e)       
            #continue   
			ss = '0'
            #break
    return ss
def uploadToS3(file_name):
    filepath = file_name + file_extension
    camera.capture(filepath)
    conn = tinys3.Connection(access_key_id, secret_access_key)
    f = open(filepath, 'rb')
    #print conn.upload(filepath, f, bucket_name)
    #print ("ashiap")
    #print conn.get(filepath,bucket_name)
    print conn.upload(filepath, f, bucket_name,
               headers={
               'x-amz-meta-cache-control': 'max-age=60'
               })
    if os.path.exists(filepath):
        os.remove(filepath)

# Custom MQTT message callback
def photoVerificationCallback(client, userdata, message):
    print("Received a new message: ")
    data = json.loads(message.payload)
    try:
        similarity = data[1][0]['Similarity']
        print("Received similarity: " + str(similarity))
        if(similarity >= 90):
            print("Access allowed, opening doors.")
            print("Thank you!")
            display.lcd_clear()
            lcd_display_stringlay.lcd_display_string("Selamat datang ado", 1)
            os.system('mpg321 iot_virginia/welcome.mp3 &')
            time.sleep(2)
            p.ChangeDutyCycle(12.5)
            time.sleep(3)
            p.ChangeDutyCycle(2.5)
            time.sleep(0.5)
            display.lcd_clear()

    except:
		print("tidak dikenal")
    print("Finished processing event.")

def checkRFIDNumber(rfidnumber):
    return rfidnumber == '4F 05 3D F6'

# Connect and subscribe to AWS IoT
myAWSIoTMQTTClient.connect()
myAWSIoTMQTTClient.subscribe("rekognition/result", 1, photoVerificationCallback)
time.sleep(2)


# Publish to the same topic in a loop forever
while True:
    print("waiting..")
    lcd_display_stringlay.lcd_display_string("Waiting .......... RFID", 1)
    display.lcd_display_string(str(datetime.datetime.now().time()),2)
    time.sleep(1)

    scan = scanRFID()
    try:
        if(scan != '0'):
    		print(scan)
    		if(checkRFIDNumber(scan)):
    			print("RFID correct, taking photo...")
    			uploadToS3(scan)
    		else:
    			print("Bad RFID - Access Denied")
    except KeyboardInterrupt:
        p.stop()
        GPIO.cleanup()
