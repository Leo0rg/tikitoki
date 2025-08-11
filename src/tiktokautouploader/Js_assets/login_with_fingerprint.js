const { chromium } = require('playwright-extra');
const fs = require('fs');
const { newInjectedContext } = require('fingerprint-injector');
const { FingerprintGenerator } = require('fingerprint-generator');

async function loginAndSaveCookies(accountName, proxy) {
    const fingerprintGenerator = new FingerprintGenerator({
        devices: ['desktop'],
        operatingSystems: ['windows'],
        browsers: [{ name: 'chrome', minVersion: 115 }],
    });
    const fingerprint = fingerprintGenerator.getFingerprint();
    
    const browser = await chromium.launch({ 
        headless: false,
        proxy: proxy 
    });

    const context = await newInjectedContext(browser, {
        fingerprint: fingerprint
    });

    const page = await context.newPage();

    try {
        // --- WARM-UP PHASE ---
        console.log('Warming up session...');
        await page.goto('https://www.tiktok.com/explore', { waitUntil: 'networkidle' });
        await new Promise(resolve => setTimeout(resolve, Math.random() * 2000 + 3000)); // wait 3-5s
        await page.mouse.wheel(0, 1500); // scroll down
        await new Promise(resolve => setTimeout(resolve, Math.random() * 1000 + 2000)); // wait 2-3s
        console.log('Warm-up complete. Navigating to login page.');
        // --- END WARM-UP ---
        
        await page.goto('https://www.tiktok.com/login/qrcode');
        
        const qrCodeElement = await page.waitForSelector('canvas', { timeout: 30000 });
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        const screenshotBuffer = await qrCodeElement.screenshot();
        const base64Screenshot = screenshotBuffer.toString('base64');
        
        // Send QR code to stdout for Python script to capture
        console.log(`QR_CODE_DATA:${base64Screenshot}`);

        await page.waitForURL('https://www.tiktok.com/foryou*', { timeout: 120000 });

        const cookies = await context.cookies();
        fs.writeFileSync(`TK_cookies_${accountName}.json`, JSON.stringify(cookies, null, 2));
        
        console.log('LOGIN_SUCCESS');

    } catch (error) {
        console.error(`LOGIN_ERROR: ${error.message}`);
    } finally {
        await browser.close();
    }
}

const accountName = process.argv[2];
const proxy = process.argv[3] ? JSON.parse(process.argv[3]) : undefined;

loginAndSaveCookies(accountName, proxy); 