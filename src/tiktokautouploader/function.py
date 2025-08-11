import asyncio
import base64
from playwright.async_api import async_playwright
import json
import time
import subprocess
from inference_sdk import InferenceHTTPClient
import pkg_resources
import requests
from PIL import Image
import sys
import os
import warnings
warnings.simplefilter("ignore")

rk = "" # Roboflow API Key
showedup = False


def check_for_updates():
    current_version = pkg_resources.get_distribution("tiktokautouploader").version
    response = requests.get("https://pypi.org/pypi/tiktokautouploader/json")
    
    if response.status_code == 200:
        latest_version = response.json()["info"]["version"]
        if current_version != latest_version:
            print(f"WARNING: You are using version {current_version} of tiktokautouploader, "
                  f"PLEASE UPDATE TO LATEST VERSION {latest_version} FOR BEST EXPERIENCE.")

def login_warning(accountname):
    print(f"NO COOKIES FILE FOUND FOR ACCOUNT {accountname}, PLEASE LOG-IN TO {accountname} WHEN PROMPTED")

def save_cookies(cookies):
    with open('TK_cookies.json', 'w') as file:
        json.dump(cookies, file, indent=4)

def check_expiry(accountname):
    with open(f'TK_cookies_{accountname}.json', 'r') as file:
        cookies = json.load(file)

    current_time = int(time.time())
    cookies_expire = []
    expired = False
    for cookie in cookies:
        if cookie['name'] in ['sessionid', 'sid_tt', 'sessionid_ss', 'passport_auth_status']:
            expiry = cookie.get('expires')
            # for manually extracted cookies
            if not expiry:
                expiry = cookie.get('expirationDate')
            cookies_expire.append(expiry < current_time)

    if all(cookies_expire):
        expired = True

    return expired


async def login_with_qr_and_save_cookies(accountname, proxy, qr_callback):
    script_path = os.path.join(os.path.dirname(__file__), 'Js_assets', 'login_with_fingerprint.js')
    cmd = ['node', script_path, accountname]
    if proxy:
        cmd.append(json.dumps(proxy))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    async for line in process.stdout:
        decoded_line = line.decode('utf-8').strip()
        if decoded_line.startswith('QR_CODE_DATA:'):
            base64_screenshot = decoded_line.replace('QR_CODE_DATA:', '')
            data_uri = f"data:image/png;base64,{base64_screenshot}"
            if qr_callback:
                await qr_callback(data_uri)
        elif decoded_line == 'LOGIN_SUCCESS':
            await process.wait()
            return True, "Авторизация прошла успешно!"

    async for line in process.stderr:
        error_message = f"Ошибка в скрипте авторизации: {line.decode('utf-8').strip()}"
        print(error_message)
    
    await process.wait()
    return False, "Произошла ошибка во время авторизации. Проверьте логи для деталей."


def read_cookies(cookies_path):
        cookie_read = False
        try:
            with open(cookies_path , 'r') as cookiefile:
                cookies = json.load(cookiefile)

            for cookie in cookies:
                if cookie.get('sameSite') not in ['Strict', 'Lax', 'None']:
                    cookie['sameSite'] = 'Lax'

            cookie_read = True
        except:
            raise Exception("ERROR: CANT READ COOKIES FILE")
        
        return cookies, cookie_read

def detect_redirect(page):
    redirect_detected = False

    def on_response(response):
        nonlocal redirect_detected
        if response.request.redirected_from:
            redirect_detected = True

    page.on('response', on_response)

    return redirect_detected

def understood_Qs(question):
    understood_terms = {
        'touchdowns' : 'football',
        'orange and round': 'basketball',
        'used in hoops': 'basketball',
        'has strings': 'guitar',
        'oval and inflatable': 'football',
        'strumming': 'guitar',
        'bounces': 'basketball',
        'musical instrument': 'guitar',
        'laces': 'football',
        'bands': 'guitar',
        'leather': 'football',
        'leaves':'tree',
        'pages': 'book',
        'throwing': 'football',
        'tossed in a spiral': 'football',
        'spiky crown': 'pineapple',
        'pigskin': 'football',
        'photography': 'camera',
        'lens': 'camera',
        'grow': 'tree',
        'captures images': 'camera',
        'keeps doctors': 'apple',
        'crown': 'pineapple',
        'driven': 'car',
        }
    
    for key in understood_terms.keys():
        if key in question:
            item = understood_terms.get(key)
            return item
        
    return 'N.A'
            


def get_image_src(page):
    image_url = page.get_attribute("img#captcha-verify-image", "src")
    return image_url

def download_image(image_url):
    response = requests.get(image_url)
    image_path = "captcha_image.jpg"
    with open(image_path, "wb") as f:
        f.write(response.content)
    return image_path

def run_inference_on_image_tougher(image_path, object):

    #rk <- Roboflow key
    
    CLIENT = InferenceHTTPClient(
        api_url="https://detect.roboflow.com",
        api_key=f"{rk}"
    )

    results = CLIENT.infer(image_path, model_id="captcha-2-6ehbe/2")

    class_names = []
    bounding_boxes = []
    for obj in results['predictions']:
        class_names.append(obj['class'])
        bounding_boxes.append({
            "x": obj['x'],
            "y": obj['y'],
            "width": obj['width'],
            "height": obj['height']
        })
    
    bounding_box = []
    class_to_click = object
    for i, classes in enumerate(class_names):
        if classes == class_to_click:
            bounding_box.append(bounding_boxes[i])
    


    return bounding_box

def run_inference_on_image(image_path):

    #rk <- Roboflow key

    CLIENT = InferenceHTTPClient(
        api_url="https://detect.roboflow.com",
        api_key=f"{rk}"
    )

    results = CLIENT.infer(image_path, model_id="tk-3nwi9/2")

    class_names = []
    bounding_boxes = []
    for obj in results['predictions']:
        class_names.append(obj['class'])
        bounding_boxes.append({
            "x": obj['x'],
            "y": obj['y'],
            "width": obj['width'],
            "height": obj['height']
        })
    
    already_written = []
    bounding_box = []
    class_to_click = []
    for i, detected_class in enumerate(class_names):
        if detected_class in already_written:
            class_to_click.append(detected_class)
            bounding_box.append(bounding_boxes[i])
            index = already_written.index(detected_class)
            bounding_box.append(bounding_boxes[index])
        
        already_written.append(detected_class)

    found = False
    if len(class_to_click) == 1:
        found = True

    return bounding_box, found

def convert_to_webpage_coordinates(bounding_boxes, image_x, image_y, image_height_web, image_width_web, image_height_real, image_width_real):

    webpage_coordinates = []
    for box in bounding_boxes:
        x_box = box['x']
        y_box = box['y']
        rel_x = (x_box * image_width_web) / image_width_real
        rel_y = (y_box * image_height_web) / image_height_real
        x_cord = image_x + rel_x 
        y_cord = image_y + rel_y
        
        webpage_coordinates.append((x_cord, y_cord))
    
    return webpage_coordinates

async def async_click_on_objects(page, object_coords):
    for (x, y) in object_coords:
        await page.mouse.click(x, y)
        await asyncio.sleep(0.5)

def validate_proxy(proxy):
    if not proxy:
        return

    if not isinstance(proxy, dict):
        raise ValueError("Proxy must be a dictionary.")

    if "server" not in proxy or not isinstance(proxy["server"], str):
        raise ValueError("Proxy must contain a 'server' key with a string value.")

    try:
        proxies = {
            "http": f'http://{proxy["server"]}/',
            "https": f'https://{proxy["server"]}/',
        }
        if proxy.get("username"):
            proxies = {
                "http": f'http://{proxy.get("username")}:{proxy.get("password")}@{proxy["server"]}/',
                "https": f'https://{proxy.get("username")}:{proxy.get("password")}@{proxy["server"]}/',
            }

        response = requests.get("https://www.google.com", proxies=proxies)
        if response.status_code == 200:
            print("Proxy is valid!")
        else:
            raise ValueError(f"Proxy test failed with status code: {response.status_code}")
    except Exception as e:
        raise ValueError(f"Invalid proxy configuration when trying to simple request: {e}")


async def upload_tiktok(video, description, accountname, qr_callback=None, hashtags=None, sound_name=None, sound_aud_vol='mix', schedule=None, day=None, copyrightcheck=False, suppressprint=False, headless=True, stealth=False, proxy=None):

    """
    UPLOADS VIDEO TO TIKTOK
    ------------------------------------------------------------------------------------------------------------------------------------------------c
    video (str) -> path to video to upload
    description (str) -> description for video
    accountname (str) -> account to upload on
    hashtags (str)(array)(opt) -> hashtags for video
    sound_name (str)(opt) -> name of tik tok sound to use for video
    sound_aud_vol (str)(opt) -> volume of tik tok sound, 'main', 'mix' or 'background', check documentation for more info -> https://github.com/haziq-exe/TikTokAutoUploader
    schedule (str)(opt) -> format HH:MM, your local time to upload video
    day (int)(opt) -> day to schedule video for, check documentation for more info -> https://github.com/haziq-exe/TikTokAutoUploader
    copyrightcheck (bool)(opt) -> include copyright check or not; CODE FAILS IF FAIL COPYRIGHT CHECK
    suppressprint (bool)(opt) -> True means function doesnt print anything to provide updates on progress
    headless (bool)(opt) -> run in headless mode or not
    stealth (bool)(opt) -> will wait second(s) before each operation
    proxy (dict)(opt) -> proxy server to run code on, check documentation for more info -> https://github.com/haziq-exe/TikTokAutoUploader
    qr_callback (coroutine)(opt) -> A coroutine to send the QR code back to the main worker.
    --------------------------------------------------------------------------------------------------------------------------------------------
    """
    try:
        check_for_updates()
    except:
        await asyncio.sleep(0.1)

    try:
        validate_proxy(proxy)
    except Exception as e:
        raise Exception(f'Error validating proxy: {e}')

    retries = 0
    cookie_read = False
    oldQ = 'N.A'

    if accountname == None:
        raise Exception("PLEASE ENTER NAME OF ACCOUNT TO POST ON, READ DOCUMENTATION FOR MORE INFO")

    if os.path.exists(f'TK_cookies_{accountname}.json'):
        cookies, cookie_read = read_cookies(cookies_path=f'TK_cookies_{accountname}.json')
        expired = check_expiry(accountname=accountname)
        if expired == True:
            os.remove(f'TK_cookies_{accountname}.json')
            print(f"COOKIES EXPIRED FOR ACCOUNT {accountname}, PLEASE LOG-IN AGAIN")
            cookie_read = False
    
    if cookie_read == False:
        login_warning(accountname=accountname)
        
        logged_in, message = await login_with_qr_and_save_cookies(accountname, proxy, qr_callback)

        if not logged_in:
            raise Exception(f"Failed to log in with QR code. {message}")

        cookies, cookie_read = read_cookies(f"TK_cookies_{accountname}.json")
        if cookie_read == False:
            raise Exception("ERROR READING COOKIES AFTER QR LOGIN")
        
 
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, proxy=proxy)
        context = await browser.new_context()
        
        await context.add_cookies(cookies)
        page = await context.new_page()
        url = 'https://www.tiktok.com/tiktokstudio/upload?from=upload&lang=en'

        if suppressprint == False:
            print(f"Uploading to account '{accountname}'")

        while retries < 2:
            try:
                await page.goto(url, timeout=30000)
            except:
                retries +=1
                await asyncio.sleep(5)
                if retries == 2:
                    raise Exception("ERROR: TIK TOK PAGE FAILED TO LOAD, try again.")
            else:
                break

        # Handle cookie consent banner
        try:
            if suppressprint == False:
                print("Checking for cookie consent banner...")
            
            allow_button = page.get_by_role("button", name="Allow all", exact=False).nth(0)
            await allow_button.wait_for(timeout=5000) # Wait up to 5 seconds
            
            if await allow_button.is_visible():
                if suppressprint == False:
                    print("Cookie consent banner detected. Clicking 'Allow all'.")
                if stealth == True:
                    await asyncio.sleep(1)
                await allow_button.click()
                await asyncio.sleep(2) # Give time for the banner to disappear
        except Exception:
            if suppressprint == False:
                print("Cookie consent banner not found or already accepted, continuing.")

        detected = False
        captcha = False
        while detected == False:
            if await page.locator('.upload-text-container').is_visible():
                detected = True
            else:
                if await page.locator('div.VerifyBar___StyledDiv-sc-12zaxoy-0.hRJhHT').is_visible():
                    detected = True
                    captcha = True
                else:
                    await asyncio.sleep(0.1)

        if captcha == True:
            image_url = await get_image_src(page)
            if image_url:
                if suppressprint == False:
                    print("CAPTCHA DETECTED, Attempting to solve")
                solved = False
                attempts = 0
                question = await page.locator('div.VerifyBar___StyledDiv-sc-12zaxoy-0.hRJhHT').text_content()
                while solved == False:
                    attempts += 1
                    start_time = time.time()
                    while question == oldQ:
                        question = await page.locator('div.VerifyBar___StyledDiv-sc-12zaxoy-0.hRJhHT').text_content()
                        if time.time() - start_time > 2:
                            break
                    if 'Select 2 objects that are the same' in question or 'Select two objects that are the same' in question:
                        found = False
                        while found == False:
                            await page.click('span.secsdk_captcha_refresh--text')
                            image_url = await get_image_src(page)
                            img_path = download_image(image_url)
                            b_box, found = run_inference_on_image(image_path=img_path)
                    
                        with Image.open(img_path) as img:
                            image_size = img.size
                        
                        imageweb = page.locator('#captcha-verify-image')
                        await imageweb.wait_for()
                        box = await imageweb.bounding_box()
                        image_x = box['x']
                        image_y = box['y']
                        image_height_web = box['height']
                        image_width_web = box['width']
                        image_width_real, image_height_real = image_size

                        webpage_coords = convert_to_webpage_coordinates(b_box, image_x, image_y, image_height_web, image_width_web, image_height_real, image_width_real)
                        if not webpage_coords:
                            webpage_coords.append((image_x + 50, image_y + 50))
                        await async_click_on_objects(page, webpage_coords)
                        await page.click("div.verify-captcha-submit-button")
                        await asyncio.sleep(0.5)
                        if attempts > 5:
                            raise Exception("FAILED TO SOLVE CAPTCHA")
                        showedup = False
                        while showedup == False:
                            if await page.locator("div.captcha_verify_message.captcha_verify_message-pass").is_visible():
                                solved = True
                                showedup = True
                                os.remove('captcha_image.jpg')
                            if await page.locator("div.captcha_verify_message.captcha_verify_message-fail").is_visible():
                                showedup = True
                                oldQ = question
                                await page.click('span.secsdk_captcha_refresh--text')
                    else:
                        objectclick = understood_Qs(question)
                        while objectclick == 'N.A':
                            oldQ = question
                            await page.click('span.secsdk_captcha_refresh--text')
                            start_time = time.time()
                            runs = 0
                            while question == oldQ:
                                runs += 1
                                question = await page.locator('div.VerifyBar___StyledDiv-sc-12zaxoy-0.hRJhHT').text_content()
                                if runs > 1:
                                    await asyncio.sleep(1)
                                if time.time() - start_time > 2:
                                    break
                            objectclick = understood_Qs(question)
                        image_url = await get_image_src(page)
                        img_path = download_image(image_url)
                        b_box = run_inference_on_image_tougher(image_path=img_path, object=objectclick)
                    
                        with Image.open(img_path) as img:
                            image_size = img.size

                        imageweb = page.locator('#captcha-verify-image')
                        await imageweb.wait_for()
                        box = await imageweb.bounding_box()
                        image_x = box['x']
                        image_y = box['y']
                        image_height_web = box['height']
                        image_width_web = box['width']
                        image_width_real, image_height_real = image_size

                        webpage_coords = convert_to_webpage_coordinates(b_box, image_x, image_y, image_height_web, image_width_web, image_height_real, image_width_real)
                        if not webpage_coords:
                            webpage_coords.append((image_x + 50, image_y + 50))
                        await async_click_on_objects(page, webpage_coords)
                        await page.click("div.verify-captcha-submit-button")
                        await asyncio.sleep(1)                   
                        if attempts > 20:
                            raise Exception("FAILED TO SOLVE CAPTCHA")
                        showedup = False
                        while showedup == False:
                            if await page.locator("div.captcha_verify_message.captcha_verify_message-pass").is_visible():
                                solved = True
                                showedup = True
                                os.remove('captcha_image.jpg')
                                if suppressprint == False:
                                    print("CAPTCHA SOLVED")
                            if await page.locator("div.captcha_verify_message.captcha_verify_message-fail").is_visible():
                                showedup = True
                                oldQ = question
                                await page.click('span.secsdk_captcha_refresh--text')

        
        try:
            await page.set_input_files('input[type="file"][accept="video/*"]', f'{video}')
        except:
            raise Exception("ERROR: FAILED TO INPUT FILE. Possible Issues: Wifi too slow, file directory wrong, or check documentation to see if captcha is solvable")
        await page.wait_for_selector('div[data-contents="true"]')
        await page.click('div[data-contents="true"]')
        if suppressprint == False:
            print("Entered File, waiting for tiktok to load onto their server, this may take a couple of minutes, depending on your video length")
        await asyncio.sleep(0.5)
        if description == None:
            raise Exception("ERROR: PLEASE INCLUDE A DESCRIPTION")

        for _ in range(len(video) + 2):
            await page.keyboard.press("Backspace")
            await page.keyboard.press("Delete")
        
        await asyncio.sleep(0.5)

        await page.keyboard.type(description)

        for _ in range(3):
            await page.keyboard.press("Enter")

        if hashtags != None:
            for hashtag in hashtags:
                if hashtag[0] != '#':
                    hashtag = "#" + hashtag

                await page.keyboard.type(hashtag)
                await asyncio.sleep(0.5)
                try:
                    if stealth == True:
                        await asyncio.sleep(2)
                    await page.click(f'span.hash-tag-topic:has-text("{hashtag}")', timeout=1000)
                except:
                    try:
                        await page.click('span.hash-tag-topic', timeout=1000)
                    except:
                        await page.keyboard.press("Backspace")
                        try:
                            await page.click('span.hash-tag-topic', timeout=1000)
                        except:
                            if suppressprint == False:
                                print(f"Tik tok hashtag not working for {hashtag}, moving onto next")
                            await page.keyboard.type(f"{hashtag[-1]} ")
        
        if suppressprint == False:
            print("Description and Hashtags added")

        try:
            await page.wait_for_selector('button:has-text("Post")[aria-disabled="false"]', timeout=12000000)
        except:
            raise Exception("ERROR: TIK TOK TOOK TOO LONG TO UPLOAD YOUR FILE (>20min). Try again, if issue persists then try a lower file size or different wifi connection")

        await asyncio.sleep(0.2)
        if suppressprint == False:
            print("Tik tok done loading file onto servers")
        
        if (schedule == None) and (day != None):
            raise Exception("ERROR: CANT SCHEDULE FOR ANOTHER DAY USING 'day' WITHOUT ALSO INCLUDING TIME OF UPLOAD WITH 'schedule'; PLEASE ALSO INCLUDE TIME WITH 'schedule' PARAMETER")

        if schedule != None:
            try:
                hour = schedule[0:2]
                minute = schedule[3:]
                if (int(minute) % 5) != 0:
                    raise Exception("MINUTE FORMAT ERROR: PLEASE MAKE SURE MINUTE YOU SCHEDULE AT IS A MULTIPLE OF 5 UNTIL 60 (i.e: 40), VIDEO SAVED AS DRAFT")

            except:
                raise Exception("SCHEDULE TIME ERROR: PLEASE MAKE SURE YOUR SCHEDULE TIME IS A STRING THAT FOLLOWS THE 24H FORMAT 'HH:MM', VIDEO SAVED AS DRAFT")

            await page.locator('label:has-text("Schedule")').click()
            if stealth==True:
                await asyncio.sleep(2)
            visible = False
            while visible == False:
                if await page.locator('button:has-text("Allow")').nth(0).is_visible():
                    if stealth == True:
                        await asyncio.sleep(1)
                    await page.locator('button:has-text("Allow")').nth(0).click()
                    visible = True
                    await asyncio.sleep(0.1)
                else:
                    if await page.locator('div.TUXTextInputCore-trailingIconWrapper').nth(1).is_visible():
                        visible = True
                        await asyncio.sleep(0.1)
            if day != None:
                if stealth==True:
                    await asyncio.sleep(1)
                await page.locator('div.TUXTextInputCore-leadingIconWrapper:has(svg > path[d="M15 3a1 1 0 0 0-1 1v3h-1.4c-3.36 0-5.04 0-6.32.65a6 6 0 0 0-2.63 2.63C3 11.56 3 13.24 3 16.6v16.8c0 3.36 0 5.04.65 6.32a6 6 0 0 0 2.63 2.63c1.28.65 2.96.65 6.32.65h22.8c3.36 0 5.04 0 6.32-.65a6 6 0 0 0 2.63-2.63c.65-1.28.65-2.96.65-6.32V16.6c0-3.36 0-5.04-.65-6.32a6 6 0 0 0-2.63-2.63C40.44 7 38.76 7 35.4 7H34V4a1 1 0 0 0-1-1h-2a1 1 0 0 0-1 1v3H18V4a1 1 0 0 0-1-1h-2Zm-2.4 8H14v3a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1v-3h12v3a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1v-3h1.4c1.75 0 2.82 0 3.62.07a5.11 5.11 0 0 1 .86.14h.03a2 2 0 0 1 .88.91 5.11 5.11 0 0 1 .14.86c.07.8.07 1.87.07 3.62v1.9H7v-1.9c0-1.75 0-2.82.07-3.62a5.12 5.12 0 0 1 .14-.86v-.03a2 2 0 0 1 .88-.87l.03-.01a5.11 5.11 0 0 1 .86-.14c.8-.07 1.87-.07 3.62-.07ZM7 22.5h34v10.9c0 1.75 0 2.82-.07 3.62a5.11 5.11 0 0 1-.14.86v.03a2 2 0 0 1-.88.87l-.03.01a5.11 5.11 0 0 1-.86-.14c-.8.07-1.87.07-3.62.07H12.6c-1.75 0-2.82 0-3.62-.07a5.11 5.11 0 0 1-.89-.15 2 2 0 0 1-.87-.87l-.01-.03a5.12 5.12 0 0 1-.14-.86C7 36.22 7 35.15 7 33.4V22.5Z"])').click()
                await asyncio.sleep(0.2)
                try:
                    if stealth==True:
                        await asyncio.sleep(1)
                    await page.locator(f'span.day.valid:text-is("{day}")').click()
                except:
                    raise Exception("SCHEDULE DAY ERROR: ERROR WITH SCHEDULED DAY, read documentation for more information on format of day")
            try:
                await asyncio.sleep(0.2)
                await page.locator('div.TUXTextInputCore-leadingIconWrapper:has(svg > path[d="M24 2a22 22 0 1 0 0 44 22 22 0 0 0 0-44ZM6 24a18 18 0 1 1 36 0 18 18 0 0 1-36 0Z"])').click()
                await asyncio.sleep(0.2)
                await page.locator(f'.tiktok-timepicker-option-text.tiktok-timepicker-right:text-is("{minute}")').scroll_into_view_if_needed()
                await asyncio.sleep(0.2)
                if stealth==True:
                    await asyncio.sleep(2)
                await page.locator(f'.tiktok-timepicker-option-text.tiktok-timepicker-right:text-is("{minute}")').click()
                await asyncio.sleep(0.2)
                if await page.locator("div.tiktok-timepicker-time-picker-container").is_visible():
                    await asyncio.sleep(0.1)
                else:
                    await page.locator('div.TUXTextInputCore-leadingIconWrapper:has(svg > path[d="M24 2a22 22 0 1 0 0 44 22 22 0 0 0 0-44ZM6 24a18 18 0 1 1 36 0 18 18 0 0 1-36 0Z"])').click()
                await page.locator(f'.tiktok-timepicker-option-text.tiktok-timepicker-left:text-is("{hour}")').scroll_into_view_if_needed()
                if stealth == True:
                        await asyncio.sleep(2)
                await page.locator(f'.tiktok-timepicker-option-text.tiktok-timepicker-left:text-is("{hour}")').click()
                await asyncio.sleep(1)

                if suppressprint == False:
                    print("Done scheduling video")

            except:
                raise Exception("SCHEDULING ERROR: VIDEO SAVED AS DRAFT")

        sound_fail = False
        if sound_name != None:
            try:
                if stealth == True:
                        await asyncio.sleep(2)
                await page.click("div.TUXButton-label:has-text('Edit video')")
            except:
                sound_fail = True
            if sound_fail == False:
                await page.wait_for_selector("input.search-bar-input")
                await page.fill("input.search-bar-input", f"{sound_name}")
                await asyncio.sleep(0.2)
                if stealth == True:
                        await asyncio.sleep(2)
                await page.click("div.TUXButton-label:has-text('Search')")
                try:
                    await page.wait_for_selector('div.music-card-container')
                    if stealth == True:
                        await asyncio.sleep(0.5)
                    await page.click("div.music-card-container")
                    await page.wait_for_selector("div.TUXButton-label:has-text('Use')")
                    if stealth == True:
                        await asyncio.sleep(1)
                    await page.click("div.TUXButton-label:has-text('Use')")
                except:
                    raise Exception(f"ERROR: SOUND '{sound_name}' NOT FOUND")
                try:
                    await page.wait_for_selector('img[src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjEiIGhlaWdodD0iMjAiIHZpZXdCb3g9IjAgMCAyMSAyMCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTAgNy41MDE2QzAgNi42NzMxNyAwLjY3MTU3MyA2LjAwMTYgMS41IDYuMDAxNkgzLjU3NzA5QzMuODY4MDUgNi4wMDE2IDQuMTQ0NTggNS44NzQ4OCA0LjMzNDU1IDUuNjU0NDlMOC43NDI1NSAwLjU0MDUyQzkuMzQ3OCAtMC4xNjE2NjggMTAuNSAwLjI2NjM3NCAxMC41IDEuMTkzNDFWMTguOTY3MkMxMC41IDE5Ljg3NDUgOS4zODg5NCAyMC4zMTI5IDguNzY5NDIgMTkuNjVMNC4zMzE3OSAxNC45MDIxQzQuMTQyNjkgMTQuNjk5OCAzLjg3ODE2IDE0LjU4NDkgMy42MDEyMiAxNC41ODQ5SDEuNUMwLjY3MTU3MyAxNC41ODQ5IDAgMTMuOTEzNCAwIDEzLjA4NDlWNy41MDE2Wk01Ljg0OTQ1IDYuOTYwMjdDNS4yNzk1NiA3LjYyMTQzIDQuNDQ5OTcgOC4wMDE2IDMuNTc3MDkgOC4wMDE2SDJWMTIuNTg0OUgzLjYwMTIyQzQuNDMyMDMgMTIuNTg0OSA1LjIyNTY0IDEyLjkyOTUgNS43OTI5NSAxMy41MzY0TDguNSAxNi40MzI4VjMuODg1MjJMNS44NDk0NSA2Ljk2MDI3WiIgZmlsbD0iIzE2MTgyMyIgZmlsbC1vcGFjaXR5PSIwLjYiLz4KPHBhdGggZD0iTTEzLjUxNSA3LjE5MTE5QzEzLjM0MjQgNi45NzU1OSAxMy4zMzk5IDYuNjYwNTYgMTMuNTM1MiA2LjQ2NTNMMTQuMjQyMyA1Ljc1ODE5QzE0LjQzNzYgNS41NjI5MyAxNC43NTU4IDUuNTYxNzUgMTQuOTM1NiA1Ljc3MTM2QzE2Ljk5NTkgOC4xNzM2MiAxNi45OTU5IDExLjgyOCAxNC45MzU2IDE0LjIzMDNDMTQuNzU1OCAxNC40Mzk5IDE0LjQzNzYgMTQuNDM4NyAxNC4yNDIzIDE0LjI0MzVMMTMuNTM1MiAxMy41MzY0QzEzLjMzOTkgMTMuMzQxMSAxMy4zNDI0IDEzLjAyNjEgMTMuNTE1IDEyLjgxMDVDMTQuODEzIDExLjE4ODUgMTQuODEzIDguODEzMTIgMTMuNTE1IDcuMTkxMTlaIiBmaWxsPSIjMTYxODIzIiBmaWxsLW9wYWNpdHk9IjAuNiIvPgo8cGF0aCBkPSJNMTYuNzE3MiAxNi43MTgzQzE2LjUyMTkgMTYuNTIzMSAxNi41MjMxIDE2LjIwNzQgMTYuNzA3MiAxNi4wMDE3QzE5LjcyNTcgMTIuNjMgMTkuNzI1NyA3LjM3MTY4IDE2LjcwNzIgNC4wMDAwMUMxNi41MjMxIDMuNzk0MjcgMTYuNTIxOSAzLjQ3ODU4IDE2LjcxNzIgMy4yODMzMkwxNy40MjQzIDIuNTc2MjFDMTcuNjE5NSAyLjM4MDk1IDE3LjkzNyAyLjM4MDIgMTguMTIzMyAyLjU4NDA4QzIxLjkwOTkgNi43MjkyNiAyMS45MDk5IDEzLjI3MjQgMTguMTIzMyAxNy40MTc2QzE3LjkzNyAxNy42MjE1IDE3LjYxOTUgMTcuNjIwNyAxNy40MjQzIDE3LjQyNTVMMTYuNzE3MiAxNi43MTgzWiIgZmlsbD0iIzE2MTgyMyIgZmlsbC1vcGFjaXR5PSIwLjYiLz4KPC9zdmc+Cg=="]')
                    if stealth == True:
                        await asyncio.sleep(1)
                    await page.click('img[src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjEiIGhlaWdodD0iMjAiIHZpZXdCb3g9IjAgMCAyMSAyMCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTAgNy41MDE2QzAgNi42NzMxNyAwLjY3MTU3MyA2LjAwMTYgMS41IDYuMDAxNkgzLjU3NzA5QzMuODY4MDUgNi4wMDE2IDQuMTQ0NTggNS44NzQ4OCA0LjMzNDU1IDUuNjU0NDlMOC43NDI1NSAwLjU0MDUyQzkuMzQ3OCAtMC4xNjE2NjggMTAuNSAwLjI2NjM3NCAxMC41IDEuMTkzNDFWMTguOTY3MkMxMC41IDE5Ljg3NDUgOS4zODg5NCAyMC4zMTI5IDguNzY5NDIgMTkuNjVMNC4zMzE3OSAxNC45MDIxQzQuMTQyNjkgMTQuNjk5OCAzLjg3ODE2IDE0LjU4NDkgMy42MDEyMiAxNC41ODQ5SDEuNUMwLjY3MTU3MyAxNC41ODQ5IDAgMTMuOTEzNCAwIDEzLjA4NDlWNy41MDE2Wk01Ljg0OTQ1IDYuOTYwMjdDNS4yNzk1NiA3LjYyMTQzIDQuNDQ5OTcgOC4wMDE2IDMuNTc3MDkgOC4wMDE2SDJWMTIuNTg0OUgzLjYwMTIyQzQuNDMyMDMgMTIuNTg0OSA1LjIyNTY0IDEyLjkyOTUgNS43OTI5NSAxMy41MzY0TDguNSAxNi40MzI4VjMuODg1MjJMNS44NDk0NSA2Ljk2MDI3WiIgZmlsbD0iIzE2MTgyMyIgZmlsbC1vcGFjaXR5PSIwLjYiLz4KPHBhdGggZD0iTTEzLjUxNSA3LjE5MTE5QzEzLjM0MjQgNi45NzU1OSAxMy4zMzk5IDYuNjYwNTYgMTMuNTM1MiA2LjQ2NTNMMTQuMjQyMyA1Ljc1ODE5QzE0LjQzNzYgNS41NjI5MyAxNC43NTU4IDUuNTYxNzUgMTQuOTM1NiA1Ljc3MTM2QzE2Ljk5NTkgOC4xNzM2MiAxNi45OTU5IDExLjgyOCAxNC45MzU2IDE0LjIzMDNDMTQuNzU1OCAxNC40Mzk5IDE0LjQzNzYgMTQuNDM4NyAxNC4yNDIzIDE0LjI0MzVMMTMuNTM1MiAxMy41MzY0QzEzLjMzOTkgMTMuMzQxMSAxMy4zNDI0IDEzLjAyNjEgMTMuNTE1IDEyLjgxMDVDMTQuODEzIDExLjE4ODUgMTQuODEzIDguODEzMTIgMTMuNTE1IDcuMTkxMTlaIiBmaWxsPSIjMTYxODIzIiBmaWxsLW9wYWNpdHk9IjAuNiIvPgo8cGF0aCBkPSJNMTYuNzE3MiAxNi43MTgzQzE2LjUyMTkgMTYuNTIzMSAxNi41MjMxIDE2LjIwNzQgMTYuNzA3MiAxNi4wMDE3QzE5LjcyNTcgMTIuNjMgMTkuNzI1NyA3LjM3MTY4IDE2LjcwNzIgNC4wMDAwMUMxNi41MjMxIDMuNzk0MjcgMTYuNTIxOSAzLjQ3ODU4IDE2LjcxNzIgMy4yODMzMkwxNy40MjQzIDIuNTc2MjFDMTcuNjE5NSAyLjM4MDk1IDE3LjkzNyAyLjM4MDIgMTguMTIzMyAyLjU4NDA4QzIxLjkwOTkgNi43MjkyNiAyMS45MDk5IDEzLjI3MjQgMTguMTIzMyAxNy40MTc2QzE3LjkzNyAxNy42MjE1IDE3LjYxOTUgMTcuNjIwNyAxNy40MjQzIDE3LjQyNTVMMTYuNzE3MiAxNi43MTgzWiIgZmlsbD0iIzE2MTgyMyIgZmlsbC1vcGFjaXR5PSIwLjYiLz4KPC9zdmc+Cg=="]')
                    await asyncio.sleep(0.5)
                    sliders = page.locator("input.scaleInput")

                    if sound_aud_vol == 'background':
                        slider1 = sliders.nth(0)
                        bounding_box1 = await slider1.bounding_box()
                        if bounding_box1:
                            x1 = bounding_box1["x"] + (bounding_box1["width"] * 0.92)
                            y1 = bounding_box1["y"] + bounding_box1["height"] / 2
                            if stealth == True:
                                await asyncio.sleep(1)
                            await page.mouse.click(x1, y1)
                    
                        slider2 = sliders.nth(1)
                        bounding_box2 = await slider2.bounding_box()
                        if bounding_box2:
                            x2 = bounding_box2["x"] + (bounding_box2["width"] * 0.097)
                            y2 = bounding_box2["y"] + bounding_box2["height"] / 2
                            if stealth == True:
                                await asyncio.sleep(1)
                            await page.mouse.click(x2, y2)

                    if sound_aud_vol == 'main':
                        slider1 = sliders.nth(0)
                        bounding_box1 = await slider1.bounding_box()
                        if bounding_box1:
                            x1 = bounding_box1["x"] + (bounding_box1["width"] * 0.092)
                            y1 = bounding_box1["y"] + bounding_box1["height"] / 2
                            if stealth == True:
                                await asyncio.sleep(1)
                            await page.mouse.click(x1, y1)
                        slider2 = sliders.nth(1)
                        bounding_box2 = await slider2.bounding_box()
                        if bounding_box2:
                            x2 = bounding_box2["x"] + (bounding_box2["width"] * 0.92)
                            y2 = bounding_box2["y"] + bounding_box2["height"] / 2
                            if stealth == True:
                                await asyncio.sleep(1)
                            await page.mouse.click(x2, y2)   
                except:
                    raise Exception("ERROR ADJUSTING SOUND VOLUME: please try again.")

                await page.wait_for_selector("div.TUXButton-label:has-text('Save edit')")
                if stealth == True:
                        await asyncio.sleep(1)
                await page.click("div.TUXButton-label:has-text('Save edit')")
                if suppressprint == False:
                    print("Added sound")
        
        if sound_fail == False:
            await page.wait_for_selector('div[data-contents="true"]')

            if copyrightcheck == True:
                if stealth == True:
                        await asyncio.sleep(1)
                await page.locator('div[data-e2e="copyright_container"] span[data-part="thumb"]').click()
                while copyrightcheck == True:
                    await asyncio.sleep(0.2)
                    if await page.locator("span" ,has_text="No issues detected.").is_visible():
                        if suppressprint == False:
                            print("Copyright check complete")
                        break
                    if await page.locator("span", has_text="Copyright issues detected.").is_visible():
                        raise Exception("COPYRIGHT CHECK FAILED: VIDEO SAVED AS DRAFT, COPYRIGHT AUDIO DETECTED FROM TIKTOK")
            

            try:
                if schedule == None:
                    if stealth == True:
                        await asyncio.sleep(1)
                    try:
                        await page.click('button:has-text("Post")[data-e2e="post_video_button"]', timeout=2000)
                        
                        # Handle "Post now" modal
                        try:
                            if suppressprint == False:
                                print("Checking for 'Post now' confirmation modal...")
                            post_now_button = page.get_by_role("button", name="Post now", exact=True)
                            await post_now_button.wait_for(timeout=5000)
                            if await post_now_button.is_visible():
                                if suppressprint == False:
                                    print("'Post now' button found. Clicking it.")
                                if stealth == True:
                                    await asyncio.sleep(1)
                                await post_now_button.click()
                        except Exception:
                            if suppressprint == False:
                                print("'Post now' modal not found, continuing.")

                        await page.wait_for_url(url='https://www.tiktok.com/tiktokstudio/content', timeout=3000)
                    except:
                        await page.click('button:has-text("Post")[aria-disabled="false"]', timeout=2000)
                        
                        # Handle "Post now" modal in fallback
                        try:
                            if suppressprint == False:
                                print("Checking for 'Post now' confirmation modal...")
                            post_now_button = page.get_by_role("button", name="Post now", exact=True)
                            await post_now_button.wait_for(timeout=5000)
                            if await post_now_button.is_visible():
                                if suppressprint == False:
                                    print("'Post now' button found. Clicking it.")
                                if stealth == True:
                                    await asyncio.sleep(1)
                                await post_now_button.click()
                        except Exception:
                            if suppressprint == False:
                                print("'Post now' modal not found, continuing.")
                        
                        try:
                            await page.wait_for_url(url='https://www.tiktok.com/tiktokstudio/content', timeout=3000)
                        except:
                            print("POSSIBLE ERROR: Cannot confirm if uploaded successfully, Please check account in a minute or two to confirm")
                            return "Error"
                    uploaded = False
                    checks = 0
                    while uploaded == False:
                        if await page.locator(':has-text("Leaving the page does not interrupt")').nth(0).is_visible():
                            await asyncio.sleep(0.1)
                            break
                        await asyncio.sleep(0.2)
                        checks += 1
                        if checks == 25:
                            break
                else:
                    if stealth == True:
                        await asyncio.sleep(1)
                    await page.click('button:has-text("Schedule")', timeout=10000)
                    uploaded = False
                    checks = 0
                    while uploaded == False:
                        if await page.locator(':has-text("Leaving the page does not interrupt")').nth(0).is_visible():
                            await asyncio.sleep(0.2)
                            break
                        await asyncio.sleep(0.2)
                        checks += 1
                        if checks == 25:
                            break
                if suppressprint == False:
                    print("Done uploading video, NOTE: it may take a minute or two to show on TikTok")
            except:
                await asyncio.sleep(2)
                raise Exception("POSSIBLE ERROR UPLOADING: Cannot confirm if uploaded successfully, Please check account in a minute or two to confirm.")
            await asyncio.sleep(1)

            await page.close()
        else:
            try:
                if stealth == True:
                        await asyncio.sleep(1)
                await page.click('button:has-text("Save draft")', timeout=10000)
            except:
                raise Exception("SAVE AS DRAFT BUTTON NOT FOUND; Please try account that has ability to save as draft")
            
            await asyncio.sleep(0.5)
            await page.close()

            browser = await p.chromium.launch(headless=headless, proxy=proxy)

            context = await browser.new_context()
            await context.add_cookies(cookies)
            page = await context.new_page()
            url2 = 'https://www.tiktok.com/tiktokstudio/content?tab=draft'

            while retries < 2:
                try:
                    await page.goto(url2, timeout=30000)
                except:
                    retries +=1
                    await asyncio.sleep(5)
                    if retries == 2:
                        raise Exception("ERROR: TIK TOK PAGE FAILED TO LOAD, try again.")
                else:
                    break
            
            try:
                await page.wait_for_selector("path[d='M37.37 4.85a4.01 4.01 0 0 0-.99-.79 3 3 0 0 0-2.72 0c-.45.23-.81.6-1 .79a9 9 0 0 1-.04.05l-19.3 19.3c-1.64 1.63-2.53 2.52-3.35 3.47a36 36 0 0 0-4.32 6.16c-.6 1.1-1.14 2.24-2.11 4.33l-.3.6c-.4.75-.84 1.61-.8 2.43a2.5 2.5 0 0 0 2.37 2.36c.82.05 1.68-.4 2.44-.79l.59-.3c2.09-.97 3.23-1.5 4.33-2.11a36 36 0 0 0 6.16-4.32c.95-.82 1.84-1.71 3.47-3.34l19.3-19.3.05-.06a3 3 0 0 0 .78-3.71c-.22-.45-.6-.81-.78-1l-.02-.02-.03-.03-3.67-3.67a8.7 8.7 0 0 1-.06-.05ZM16.2 26.97 35.02 8.15l2.83 2.83L19.03 29.8c-1.7 1.7-2.5 2.5-3.33 3.21a32 32 0 0 1-7.65 4.93 32 32 0 0 1 4.93-7.65c.73-.82 1.51-1.61 3.22-3.32Z']")
                if stealth == True:
                        await asyncio.sleep(1)
                await page.click("path[d='M37.37 4.85a4.01 4.01 0 0 0-.99-.79 3 3 0 0 0-2.72 0c-.45.23-.81.6-1 .79a9 9 0 0 1-.04.05l-19.3 19.3c-1.64 1.63-2.53 2.52-3.35 3.47a36 36 0 0 0-4.32 6.16c-.6 1.1-1.14 2.24-2.11 4.33l-.3.6c-.4.75-.84 1.61-.8 2.43a2.5 2.5 0 0 0 2.37 2.36c.82.05 1.68-.4 2.44-.79l.59-.3c2.09-.97 3.23-1.5 4.33-2.11a36 36 0 0 0 6.16-4.32c.95-.82 1.84-1.71 3.47-3.34l19.3-19.3.05-.06a3 3 0 0 0 .78-3.71c-.22-.45-.6-.81-.78-1l-.02-.02-.03-.03-3.67-3.67a8.7 8.7 0 0 1-.06-.05ZM16.2 26.97 35.02 8.15l2.83 2.83L19.03 29.8c-1.7 1.7-2.5 2.5-3.33 3.21a32 32 0 0 1-7.65 4.93 32 32 0 0 1 4.93-7.65c.73-.82 1.51-1.61 3.22-3.32Z']")
                await page.wait_for_selector('div[data-contents="true"]')
                await asyncio.sleep(0.2)
            except:
                raise Exception("ERROR ADDING SOUND: Video saved as draft")
            
            if sound_name != None:
                    if stealth == True:
                        await asyncio.sleep(1)
                    await page.click("div.TUXButton-label:has-text('Edit video')")
                    await page.wait_for_selector("input.search-bar-input")
                    await page.fill("input.search-bar-input", f"{sound_name}")
                    await asyncio.sleep(0.2)
                    if stealth == True:
                        await asyncio.sleep(1)
                    await page.click("div.TUXButton-label:has-text('Search')")
                    try:
                        await page.wait_for_selector('div.music-card-container')
                        if stealth == True:
                            await asyncio.sleep(1)
                        await page.click("div.music-card-container")
                        await page.wait_for_selector("div.TUXButton-label:has-text('Use')")
                        if stealth == True:
                            await asyncio.sleep(1)
                        await page.click("div.TUXButton-label:has-text('Use')")
                    except:
                        raise Exception(f"ERROR: SOUND '{sound_name}' NOT FOUND")
                    try:
                        await page.wait_for_selector('img[src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjEiIGhlaWdodD0iMjAiIHZpZXdCb3g9IjAgMCAyMSAyMCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTAgNy41MDE2QzAgNi42NzMxNyAwLjY3MTU3MyA2LjAwMTYgMS41IDYuMDAxNkgzLjU3NzA5QzMuODY4MDUgNi4wMDE2IDQuMTQ0NTggNS44NzQ4OCA0LjMzNDU1IDUuNjU0NDlMOC43NDI1NSAwLjU0MDUyQzkuMzQ3OCAtMC4xNjE2NjggMTAuNSAwLjI2NjM3NCAxMC41IDEuMTkzNDFWMTguOTY3MkMxMC41IDE5Ljg3NDUgOS4zODg5NCAyMC4zMTI5IDguNzY5NDIgMTkuNjVMNC4zMzE3OSAxNC45MDIxQzQuMTQyNjkgMTQuNjk5OCAzLjg3ODE2IDE0LjU4NDkgMy42MDEyMiAxNC41ODQ5SDEuNUMwLjY3MTU3MyAxNC41ODQ5IDAgMTMuOTEzNCAwIDEzLjA4NDlWNy41MDE2Wk01Ljg0OTQ1IDYuOTYwMjdDNS4yNzk1NiA3LjYyMTQzIDQuNDQ5OTcgOC4wMDE2IDMuNTc3MDkgOC4wMDE2SDJWMTIuNTg0OUgzLjYwMTIyQzQuNDMyMDMgMTIuNTg0OSA1LjIyNTY0IDEyLjkyOTUgNS43OTI5NSAxMy41MzY0TDguNSAxNi40MzI4VjMuODg1MjJMNS44NDk0NSA2Ljk2MDI3WiIgZmlsbD0iIzE2MTgyMyIgZmlsbC1vcGFjaXR5PSIwLjYiLz4KPHBhdGggZD0iTTEzLjUxNSA3LjE5MTE5QzEzLjM0MjQgNi45NzU1OSAxMy4zMzk5IDYuNjYwNTYgMTMuNTM1MiA2LjQ2NTNMMTQuMjQyMyA1Ljc1ODE5QzE0LjQzNzYgNS41NjI5MyAxNC43NTU4IDUuNTYxNzUgMTQuOTM1NiA1Ljc3MTM2QzE2Ljk5NTkgOC4xNzM2MiAxNi45OTU5IDExLjgyOCAxNC45MzU2IDE0LjIzMDNDMTQuNzU1OCAxNC40Mzk5IDE0LjQzNzYgMTQuNDM4NyAxNC4yNDIzIDE0LjI0MzVMMTMuNTM1MiAxMy41MzY0QzEzLjMzOTkgMTMuMzQxMSAxMy4zNDI0IDEzLjAyNjEgMTMuNTE1IDEyLjgxMDVDMTQuODEzIDExLjE4ODUgMTQuODEzIDguODEzMTIgMTMuNTE1IDcuMTkxMTlaIiBmaWxsPSIjMTYxODIzIiBmaWxsLW9wYWNpdHk9IjAuNiIvPgo8cGF0aCBkPSJNMTYuNzE3MiAxNi43MTgzQzE2LjUyMTkgMTYuNTIzMSAxNi41MjMxIDE2LjIwNzQgMTYuNzA3MiAxNi4wMDE3QzE5LjcyNTcgMTIuNjMgMTkuNzI1NyA3LjM3MTY4IDE2LjcwNzIgNC4wMDAwMUMxNi41MjMxIDMuNzk0MjcgMTYuNTIxOSAzLjQ3ODU4IDE2LjcxNzIgMy4yODMzMkwxNy40MjQzIDIuNTc2MjFDMTcuNjE5NSAyLjM4MDk1IDE3LjkzNyAyLjM4MDIgMTguMTIzMyAyLjU4NDA4QzIxLjkwOTkgNi43MjkyNiAyMS45MDk5IDEzLjI3MjQgMTguMTIzMyAxNy40MTc2QzE3LjkzNyAxNy42MjE1IDE3LjYxOTUgMTcuNjIwNyAxNy40MjQzIDE3LjQyNTVMMTYuNzE3MiAxNi43MTgzWiIgZmlsbD0iIzE2MTgyMyIgZmlsbC1vcGFjaXR5PSIwLjYiLz4KPC9zdmc+Cg=="]')
                        if stealth == True:
                            await asyncio.sleep(1)
                        await page.click('img[src="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjEiIGhlaWdodD0iMjAiIHZpZXdCb3g9IjAgMCAyMSAyMCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTAgNy41MDE2QzAgNi42NzMxNyAwLjY3MTU3MyA2LjAwMTYgMS41IDYuMDAxNkgzLjU3NzA5QzMuODY4MDUgNi4wMDE2IDQuMTQ0NTggNS44NzQ4OCA0LjMzNDU1IDUuNjU0NDlMOC43NDI1NSAwLjU0MDUyQzkuMzQ3OCAtMC4xNjE2NjggMTAuNSAwLjI2NjM3NCAxMC41IDEuMTkzNDFWMTguOTY3MkMxMC41IDE5Ljg3NDUgOS4zODg5NCAyMC4zMTI5IDguNzY5NDIgMTkuNjVMNC4zMzE3OSAxNC45MDIxQzQuMTQyNjkgMTQuNjk5OCAzLjg3ODE2IDE0LjU4NDkgMy42MDEyMiAxNC41ODQ5SDEuNUMwLjY3MTU3MyAxNC41ODQ5IDAgMTMuOTEzNCAwIDEzLjA4NDlWNy41MDE2Wk01Ljg0OTQ1IDYuOTYwMjdDNS4yNzk1NiA3LjYyMTQzIDQuNDQ5OTcgOC4wMDE2IDMuNTc3MDkgOC4wMDE2SDJWMTIuNTg0OUgzLjYwMTIyQzQuNDMyMDMgMTIuNTg0OSA1LjIyNTY0IDEyLjkyOTUgNS43OTI5NSAxMy41MzY0TDguNSAxNi40MzI4VjMuODg1MjJMNS44NDk0NSA2Ljk2MDI3WiIgZmlsbD0iIzE2MTgyMyIgZmlsbC1vcGFjaXR5PSIwLjYiLz4KPHBhdGggZD0iTTEzLjUxNSA3LjE5MTE5QzEzLjM0MjQgNi45NzU1OSAxMy4zMzk5IDYuNjYwNTYgMTMuNTM1MiA2LjQ2NTNMMTQuMjQyMyA1Ljc1ODE5QzE0LjQzNzYgNS41NjI5MyAxNC43NTU4IDUuNTYxNzUgMTQuOTM1NiA1Ljc3MTM2QzE2Ljk5NTkgOC4xNzM2MiAxNi45OTU5IDExLjgyOCAxNC45MzU2IDE0LjIzMDNDMTQuNzU1OCAxNC40Mzk5IDE0LjQzNzYgMTQuNDM4NyAxNC4yNDIzIDE0LjI0MzVMMTMuNTM1MiAxMy41MzY0QzEzLjMzOTkgMTMuMzQxMSAxMy4zNDI0IDEzLjAyNjEgMTMuNTE1IDEyLjgxMDVDMTQuODEzIDExLjE4ODUgMTQuODEzIDguODEzMTIgMTMuNTE1IDcuMTkxMTlaIiBmaWxsPSIjMTYxODIzIiBmaWxsLW9wYWNpdHk9IjAuNiIvPgo8cGF0aCBkPSJNMTYuNzE3MiAxNi43MTgzQzE2LjUyMTkgMTYuNTIzMSAxNi41MjMxIDE2LjIwNzQgMTYuNzA3MiAxNi4wMDE3QzE5LjcyNTcgMTIuNjMgMTkuNzI1NyA3LjM3MTY4IDE2LjcwNzIgNC4wMDAwMUMxNi41MjMxIDMuNzk0MjcgMTYuNTIxOSAzLjQ3ODU4IDE2LjcxNzIgMy4yODMzMkwxNy40MjQzIDIuNTc2MjFDMTcuNjE5NSAyLjM4MDk1IDE3LjkzNyAyLjM4MDIgMTguMTIzMyAyLjU4NDA4QzIxLjkwOTkgNi43MjkyNiAyMS45MDk5IDEzLjI3MjQgMTguMTIzMyAxNy40MTc2QzE3LjkzNyAxNy42MjE1IDE3LjYxOTUgMTcuNjIwNyAxNy40MjQzIDE3LjQyNTVMMTYuNzE3MiAxNi43MTgzWiIgZmlsbD0iIzE2MTgyMyIgZmlsbC1vcGFjaXR5PSIwLjYiLz4KPC9zdmc+Cg=="]')
                        await asyncio.sleep(0.5)
                        sliders = page.locator("input.scaleInput")

                        if sound_aud_vol == 'background':
                            slider1 = sliders.nth(0)
                            bounding_box1 = await slider1.bounding_box()
                            if bounding_box1:
                                x1 = bounding_box1["x"] + (bounding_box1["width"] * 0.92)
                                y1 = bounding_box1["y"] + bounding_box1["height"] / 2
                                if stealth == True:
                                    await asyncio.sleep(1)
                                await page.mouse.click(x1, y1)
                        
                            slider2 = sliders.nth(1)
                            bounding_box2 = await slider2.bounding_box()
                            if bounding_box2:
                                x2 = bounding_box2["x"] + (bounding_box2["width"] * 0.097)
                                y2 = bounding_box2["y"] + bounding_box2["height"] / 2
                                if stealth == True:
                                    await asyncio.sleep(1)
                                await page.mouse.click(x2, y2)

                        if sound_aud_vol == 'main':
                            slider1 = sliders.nth(0)
                            bounding_box1 = await slider1.bounding_box()
                            if bounding_box1:
                                x1 = bounding_box1["x"] + (bounding_box1["width"] * 0.092)
                                y1 = bounding_box1["y"] + bounding_box1["height"] / 2
                                if stealth == True:
                                    await asyncio.sleep(1)
                                await page.mouse.click(x1, y1)
                            slider2 = sliders.nth(1)
                            bounding_box2 = await slider2.bounding_box()
                            if bounding_box2:
                                x2 = bounding_box2["x"] + (bounding_box2["width"] * 0.92)
                                y2 = bounding_box2["y"] + bounding_box2["height"] / 2
                                if stealth == True:
                                    await asyncio.sleep(1)
                                await page.mouse.click(x2, y2)   
                    except:
                        raise Exception("ERROR ADJUSTING SOUND VOLUME: please try again.")

                    await page.wait_for_selector("div.TUXButton-label:has-text('Save edit')")
                    if stealth == True:
                        await asyncio.sleep(1)
                    await page.click("div.TUXButton-label:has-text('Save edit')")
                    if suppressprint == False:
                        print("Added sound")
        

            await page.wait_for_selector('div[data-contents="true"]')

            if copyrightcheck == True:
                if stealth == True:
                        await asyncio.sleep(1)
                await page.locator('div[data-e2e="copyright_container"] span[data-part="thumb"]').click()
                while copyrightcheck == True:
                    await asyncio.sleep(0.2)
                    if await page.locator("span", has_text="No issues detected.").is_visible():
                        if suppressprint == False:
                            print("Copyright check complete")
                        break
                    if await page.locator('span', has_text="Copyright issues detected.").is_visible():
                        raise Exception("COPYRIGHT CHECK FAILED: VIDEO SAVED AS DRAFT, COPYRIGHT AUDIO DETECTED FROM TIKTOK")
            

            try:
                if schedule == None:
                    if stealth == True:
                        await asyncio.sleep(1)
                    try:
                        await page.click('button:has-text("Post")[data-e2e="post_video_button"]', timeout=2000)
                        
                        # Handle "Post now" modal
                        try:
                            if suppressprint == False:
                                print("Checking for 'Post now' confirmation modal...")
                            post_now_button = page.get_by_role("button", name="Post now", exact=True)
                            await post_now_button.wait_for(timeout=5000)
                            if await post_now_button.is_visible():
                                if suppressprint == False:
                                    print("'Post now' button found. Clicking it.")
                                if stealth == True:
                                    await asyncio.sleep(1)
                                await post_now_button.click()
                        except Exception:
                            if suppressprint == False:
                                print("'Post now' modal not found, continuing.")

                        await page.wait_for_url(url='https://www.tiktok.com/tiktokstudio/content', timeout=3000)
                    except:
                        await page.click('button:has-text("Post")[aria-disabled="false"]', timeout=2000)
                        
                        # Handle "Post now" modal in fallback
                        try:
                            if suppressprint == False:
                                print("Checking for 'Post now' confirmation modal...")
                            post_now_button = page.get_by_role("button", name="Post now", exact=True)
                            await post_now_button.wait_for(timeout=5000)
                            if await post_now_button.is_visible():
                                if suppressprint == False:
                                    print("'Post now' button found. Clicking it.")
                                if stealth == True:
                                    await asyncio.sleep(1)
                                await post_now_button.click()
                        except Exception:
                            if suppressprint == False:
                                print("'Post now' modal not found, continuing.")
                        
                        try:
                            await page.wait_for_url(url='https://www.tiktok.com/tiktokstudio/content', timeout=3000)
                        except:
                            print("POSSIBLE ERROR: Cannot confirm if uploaded successfully, Please check account in a minute or two to confirm")
                            return "Error"
                    uploaded = False
                    checks = 0
                    while uploaded == False:
                        if await page.locator(':has-text("Leaving the page does not interrupt")').nth(0).is_visible():
                            await asyncio.sleep(0.2)
                            break
                        await asyncio.sleep(0.2)
                        checks += 1
                        if checks == 25:
                            break
                else:
                    if stealth == True:
                        await asyncio.sleep(1)
                    await page.click('button:has-text("Schedule")', timeout=10000)
                    uploaded = False
                    checks = 0
                    while uploaded == False:
                        if await page.locator(':has-text("Leaving the page does not interrupt")').nth(0).is_visible():
                            await asyncio.sleep(0.1)
                            break
                        await asyncio.sleep(0.2)
                        checks += 1
                        if checks == 25:
                            break
                if suppressprint == False:
                    print("Done uploading video, NOTE: it may take a minute or two to show on TikTok")
            except:
                await asyncio.sleep(2)
                raise Exception("POSSIBLE ERROR UPLOADING: Cannot confirm if uploaded successfully, Please check account in a minute or two to confirm.")
            await asyncio.sleep(1)

            await page.close()
    
    return "Completed"