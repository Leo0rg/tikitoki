const { chromium } = require('playwright-extra');
const fs = require('fs');
const { newInjectedContext } = require('fingerprint-injector');
const { FingerprintGenerator } = require('fingerprint-generator');
const { solveCaptcha } = require('./captcha_solver.js');

async function humanLikeDrag(page, start, end) {
    const { x: startX, y: startY } = start;
    const { x: endX, y: endY } = end;
    
    await page.mouse.move(startX, startY, { steps: 10 });
    await page.mouse.down();
    await new Promise(resolve => setTimeout(resolve, 200 + Math.random() * 150));

    const steps = 40 + Math.floor(Math.random() * 20);
    const distanceX = endX - startX;
    const distanceY = endY - startY;

    for (let i = 0; i <= steps; i++) {
        const t = i / steps;
        const easeT = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        
        const currentX = startX + distanceX * easeT;
        const currentY = startY + distanceY * easeT;

        const noiseFactor = Math.sin(t * Math.PI);
        const randomX = currentX + (Math.random() - 0.5) * 4 * noiseFactor;
        const randomY = currentY + (Math.random() - 0.5) * 4 * noiseFactor;

        await page.mouse.move(randomX, randomY);
        await new Promise(resolve => setTimeout(resolve, 5 + Math.random() * 10));
    }

    await new Promise(resolve => setTimeout(resolve, 250 + Math.random() * 200));
    await page.mouse.up();
}

async function handleSlideCaptcha(page) {
    return new Promise(async (resolve, reject) => {
        console.log('Setting up network listener for captcha images...');
        let captchaUrls = [];

        const responseListener = async (response) => {
            const url = response.url();
            if (url.includes('https://p16')) {
                console.log(`Captcha image URL detected: ${url}`);
                captchaUrls.push(url);

                if (captchaUrls.length === 2) {
                    page.removeListener('response', responseListener); // Stop listening
                    try {
                        console.log('Found 2 captcha images, attempting to solve...');
                        
                        const bgImageElement = page.locator('img[alt="Captcha"]').first();
                        const bgBox = await bgImageElement.boundingBox();
                        if (!bgBox) throw new Error('Could not get bounding box for background image.');

                        const viewportWidth = page.viewportSize().width;
                        const captchaWidth = viewportWidth < 640 ? 288 : 348;
                        const captchaHeight = 40;

                        const solution = await solveCaptcha({
                            captchaType: 'whirl',
                            backgroundUrl: captchaUrls[0],
                            puzzleUrl: captchaUrls[1],
                            width: captchaWidth,
                            height: captchaHeight
                        });

                        console.log(bgBox);
                        // console.log("Заглушка для тестов на x100");
                        // const solution = { x: 100, error: "0" };
                        console.log(solution);
                        
                        if (solution && solution.error === "0" && typeof solution.x !== 'undefined') {
                            console.log('Captcha solution found. Moving slider...');
                            const sliderHandle = page.locator('.secsdk-captcha-drag-icon').first();
                            const handleBox = await sliderHandle.boundingBox();

                            if (!handleBox) {
                                throw new Error('Could not get bounding box for slider.');
                            }
                            
                            const startX = handleBox.x + handleBox.width / 2;
                            const startY = handleBox.y + handleBox.height / 2;
                            
                            const targetX = bgBox.x + solution.x;

                            await humanLikeDrag(page, { x: startX, y: startY }, { x: targetX, y: startY });
                            
                            console.log('Slider moved. Waiting for verification...');
                            await new Promise(res => setTimeout(res, 3000));
                            
                            const errorLocator = page.locator('.captcha_verify_message-fail');
                            if (await errorLocator.isVisible()) {
                                reject(new Error('Captcha verification failed after slider move.'));
                            } else {
                                console.log("Captcha solved successfully.");
                                resolve(true);
                            }
                        } else {
                            reject(new Error(`Failed to get a valid solution. Response: ${JSON.stringify(solution)}`));
                        }
                    } catch (err) {
                        reject(err);
                    }
                }
            }
        };

        page.on('response', responseListener);

        // Timeout to prevent hanging indefinitely
        setTimeout(() => {
            page.removeListener('response', responseListener);
            if (captchaUrls.length < 2) {
                 console.log('Timeout: Did not find 2 captcha images in time.');
                 resolve(false); // Resolve with false instead of rejecting on timeout
            }
        }, 25000); // 25 seconds timeout
    });
}


async function loginWithCredentials(accountName, username, password, proxy) {
    const fingerprintGenerator = new FingerprintGenerator({
        devices: ['desktop'],
        operatingSystems: ['windows'],
        browsers: [{ name: 'chrome', minVersion: 115 }],
    });
    const fingerprint = fingerprintGenerator.getFingerprint();
    
    const browser = await chromium.launch({ 
        headless: false, // Run in headless mode for server environment
        proxy: proxy 
    });

    const context = await newInjectedContext(browser, {
        fingerprint: fingerprint
    });

    const page = await context.newPage();
    const client = await context.newCDPSession(page);
    await client.send('WebAuthn.enable');
    const { authenticatorId } = await client.send('WebAuthn.addVirtualAuthenticator', {
        options: {
            protocol: 'ctap2',
            transport: 'internal',
            hasResidentKey: true,
            hasUserVerification: true,
            isUserVerified: true,
            automaticPresenceSimulation: true
        }
    });

    try {
        // Warm-up phase to appear more human
        console.log('Warming up session...');
        await page.goto('https://www.tiktok.com/explore', { waitUntil: 'networkidle', timeout: 60000 });
        await new Promise(resolve => setTimeout(resolve, Math.random() * 2000 + 3000));
        await page.mouse.wheel(0, 1500);
        await new Promise(resolve => setTimeout(resolve, Math.random() * 1000 + 2000));
        console.log('Warm-up complete. Navigating to login page.');
        
        await page.goto('https://www.tiktok.com/login/phone-or-email/email', { timeout: 60000 });
        
        const usernameLocator = page.locator('input[name="username"]');
        await usernameLocator.waitFor({ state: 'visible', timeout: 30000 });
        console.log('Typing username...');
        await usernameLocator.pressSequentially(username, { delay: 100 });
        
        const passwordLocator = page.locator('input[type="password"]');
        await passwordLocator.waitFor({ state: 'visible', timeout: 30000 });
        // Log the password to verify it's received correctly, but be mindful of security in production logs.
        console.log(`Received password: ${password ? 'Yes' : 'No'}`); 
        console.log('Typing password...');
        await passwordLocator.pressSequentially(password, { delay: 100 });

        await new Promise(resolve => setTimeout(resolve, 500));

        await page.locator('button[data-e2e="login-button"]').click();

        try {
            const captchaSolved = await handleSlideCaptcha(page);
            if (!captchaSolved) {
                 console.log("Captcha was not detected or not solved, proceeding to check for login success...");
            }
        } catch(error) {
            console.error(`An error occurred while handling the captcha: ${error.message}`);
            // Decide if this should be a fatal error
        }
        
        // After attempting captcha, wait a bit for the page to react
        await new Promise(resolve => setTimeout(resolve, 5000)); 

        // Check for error message first
        const errorLocator = page.locator('.tiktok-y6p5ss-DivErrorContainer, .errorMessage');
        const isErrorVisible = await errorLocator.isVisible();

        if (isErrorVisible) {
            const errorMessage = await errorLocator.textContent();
            throw new Error(errorMessage || 'Invalid credentials or CAPTCHA required.');
        }

        // If no error, wait for successful navigation to the feed.
        await page.waitForURL('https://www.tiktok.com/foryou*', { timeout: 60000 });

        const cookies = await context.cookies();
        fs.writeFileSync(`TK_cookies_${accountName}.json`, JSON.stringify(cookies, null, 2));
        
        console.log('LOGIN_SUCCESS');

    } catch (error) {
        console.error(`LOGIN_ERROR: ${error.message}`);
    } finally {
        await client.send('WebAuthn.removeVirtualAuthenticator', { authenticatorId });
        await browser.close();
    }
}

// Parse arguments
const accountName = process.argv[2];
const username = process.argv[3];
const password = process.argv[4];
// Proxy is an optional JSON string
const proxyArg = process.argv[5];
let proxy;
if (proxyArg) {
    try {
        proxy = JSON.parse(proxyArg);
    } catch (e) {
        console.error(`LOGIN_ERROR: Could not parse proxy JSON: ${e.message}`);
        process.exit(1);
    }
}

if (!accountName || !username || !password) {
    console.error('LOGIN_ERROR: Missing arguments. Usage: node login_automated.js <accountName> <username> <password> [proxyJsonString]');
    process.exit(1);
}

loginWithCredentials(accountName, username, password, proxy); 