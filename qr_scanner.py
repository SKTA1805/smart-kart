from imutils.video import VideoStream
from pyzbar import pyzbar
import argparse
import datetime
import imutils
import time
import cv2
import RPi.GPIO as GPIO
import urllib.request
import json
import urllib.parse
from picamera2 import Picamera2

# -----------------------------
# GPIO SETUP
# -----------------------------a
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

but = 2            # Button to end session
buz = 21           # Buzzer output
ir = 17            # IR LED (or similar)
GPIO.setup(but, GPIO.IN)
GPIO.setup(buz, GPIO.OUT)
GPIO.setup(ir, GPIO.OUT)
GPIO.output(buz, 1)

# -----------------------------
# LCD SETUP
# -----------------------------
LCD_RS = 26
LCD_E = 19
LCD_D4 = 13
LCD_D5 = 6
LCD_D6 = 5
LCD_D7 = 11
GPIO.setup(LCD_E, GPIO.OUT)
GPIO.setup(LCD_RS, GPIO.OUT)
GPIO.setup(LCD_D4, GPIO.OUT)
GPIO.setup(LCD_D5, GPIO.OUT)
GPIO.setup(LCD_D6, GPIO.OUT)
GPIO.setup(LCD_D7, GPIO.OUT)

LCD_WIDTH = 16
LCD_CHR = True
LCD_CMD = False
LCD_LINE_1 = 0x80
LCD_LINE_2 = 0xC0
E_PULSE = 0.0005
E_DELAY = 0.0005

def lcd_init():
    lcd_byte(0x33, LCD_CMD)
    lcd_byte(0x32, LCD_CMD)
    lcd_byte(0x06, LCD_CMD)
    lcd_byte(0x0C, LCD_CMD)
    lcd_byte(0x28, LCD_CMD)
    lcd_byte(0x01, LCD_CMD)
    time.sleep(E_DELAY)

def lcd_byte(bits, mode):
    GPIO.output(LCD_RS, mode)
    for pin, bit in zip([LCD_D4, LCD_D5, LCD_D6, LCD_D7], [0x10, 0x20, 0x40, 0x80]):
        GPIO.output(pin, bool(bits & bit))
    lcd_toggle_enable()
    for pin, bit in zip([LCD_D4, LCD_D5, LCD_D6, LCD_D7], [0x01, 0x02, 0x04, 0x08]):
        GPIO.output(pin, bool(bits & bit))
    lcd_toggle_enable()

def lcd_toggle_enable():
    time.sleep(E_DELAY)
    GPIO.output(LCD_E, True)
    time.sleep(E_PULSE)
    GPIO.output(LCD_E, False)
    time.sleep(E_DELAY)

def lcd_string(message, line):
    message = message.ljust(LCD_WIDTH, " ")
    lcd_byte(line, LCD_CMD)
    for char in message:
        lcd_byte(ord(char), LCD_CHR)

lcd_init()
lcd_byte(0x01, LCD_CMD)

# -----------------------------
# GET PHONE NUMBER & DISPLAY
# -----------------------------
uname = input('ENTER Ph.No: ')
lcd_string("Phone: " + uname, LCD_LINE_1)
time.sleep(0.5)
lcd_string("Scan prod:", LCD_LINE_1)

# -----------------------------
# CAMERA SETUP
# -----------------------------
try:
    picam2 = Picamera2()
    picam2.configure(picam2.create_video_configuration(main={"size": (640, 480)}))
    picam2.start()
except Exception as e:
    print(f"⚠️ Camera initialization failed: {e}")
    GPIO.cleanup()
    exit()

# -----------------------------
# ARGUMENT PARSER (CSV output file)
# -----------------------------
ap = argparse.ArgumentParser()
ap.add_argument("-o", "--output", type=str, default="barcodes.csv", help="path to output CSV file containing barcodes")
args = vars(ap.parse_args())

# -----------------------------
# VARIABLES
# -----------------------------
time.sleep(2.0)
csv = open(args["output"], "w")
found = {}            # To store timestamp of each scanned QR to prevent duplicate scans within 10 secs
prod = []             # List to store product details
tcost = 0             # Total cost
pc = 0                # Product count
GPIO.output(ir, 0)
last_detected = {}    # To store bounding box details for red box display
scan_delay = 10       # 10 seconds delay between scans for same QR code

# -----------------------------
# FUNCTION: SEND SCANNED PRODUCT TO SERVER
# -----------------------------
def send_to_server(product_name, price):
    url = "http://smart-kart.onrender.com/update-cart"  # Change to your server's IP if needed
    data = {"name": product_name, "price": price}
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        response = urllib.request.urlopen(req)
        print("✅ Product updated on website:", response.read().decode())
    except urllib.error.URLError as e:
        print("⚠️ Could not reach the server:", e)

# -----------------------------
# MAIN LOOP: SCAN & PROCESS QR CODES
# -----------------------------
while True:
    img = picam2.capture_array()
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    frame = imutils.resize(img, width=400)
    barcodes = pyzbar.decode(frame)
    current_time = time.time()
    
    for barcode in barcodes:
        (x, y, w, h) = barcode.rect
        barcodeData = barcode.data.decode("utf-8")
        
        # Parse the QR code data expecting "Product-Price"
        try:
            pname, pcost = barcodeData.split('-')
            pcost = int(pcost)
        except ValueError:
            print("⚠️ Invalid QR format. Use: 'Product-Price'")
            continue

        # Prevent multiple detections within 10 seconds for the same QR
        if barcodeData in found and (current_time - found[barcodeData]) < scan_delay:
            continue
        
        # Record the scan time and update bounding box information
        found[barcodeData] = current_time
        last_detected[barcodeData] = (x, y, w, h, current_time)
        
        # Update totals and product list
        tcost += pcost
        prod.append({"name": pname, "cost": pcost})
        pc += 1
        
        # Send the scanned product to the server
        send_to_server(pname, pcost)
        
        # Activate buzzer and update LCD
        GPIO.output(ir, 1)
        GPIO.output(buz, 1)
        time.sleep(0.1)
        GPIO.output(buz, 0)
        lcd_byte(0x01, LCD_CMD)
        lcd_string(pname, LCD_LINE_1)
        lcd_string(f"TB: {tcost} C: {pc}", LCD_LINE_2)
        lcd_string("Scan prod: ", LCD_LINE_1)
        GPIO.output(ir, 0)
        
        # Print scanned product details to terminal
        print(f"✅ Product Name: {pname}, Cost: {pcost}, Total Bill: {tcost}, Items: {pc}")

    # Draw red bounding box that follows QR code movement
    for barcodeData, (x, y, w, h, detect_time) in list(last_detected.items()):
        if current_time - detect_time < 5:  # Keep the box for at least 5 seconds
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
            cv2.putText(frame, barcodeData.split('-')[0], (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        else:
            del last_detected[barcodeData]

    cv2.imshow("Barcode Reader", frame)
    key = cv2.waitKey(1) & 0xFF

    # End session when 's' key is pressed or physical button is pressed
    if key == ord("s") or GPIO.input(but) == 0:
        # Optional: send final summary if needed (here we just display a thank you message)
        lcd_string("Thank U 4 Shpng!", LCD_LINE_1)
        print("🛒 Thank you for shopping!")
        break

cv2.destroyAllWindows()
GPIO.cleanup()
print("🔴 Scanner Stopped & GPIO Cleaned")
