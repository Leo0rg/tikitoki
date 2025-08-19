const fetch = require('node-fetch');

const RAPIDAPI_KEY = process.env.RAPIDAPI_KEY;
const RAPIDAPI_HOST = 'tiktok-captcha-solver6.p.rapidapi.com';

async function urlToB64(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`Failed to fetch image from ${url}: ${response.statusText}`);
    }
    const buffer = await response.buffer();
    return buffer.toString('base64');
}

async function solveCaptcha(options) {
    const { captchaType, backgroundUrl, puzzleUrl, imageBase64, width, height, question } = options;
    let endpoint = '';
    let payload;

    switch (captchaType) {
        case 'whirl':
            if (!backgroundUrl || !puzzleUrl || !width || !height) {
                throw new Error(`For 'whirl' captcha, all params are required.`);
            }
            endpoint = '/whirl';
            payload = {
                b64External_or_url: await urlToB64(backgroundUrl),
                b64Internal_or_url: await urlToB64(puzzleUrl),
                width: String(width),
                height: String(height),
                version: '2',
                proxy: ''
            };
            console.log(payload);
            break;
        case 'puzzle':
            if (!backgroundUrl || !puzzleUrl || !width || !height) {
                throw new Error(`For 'puzzle' captcha, all params are required.`);
            }
            endpoint = '/slide';
            payload = {
                b64External_or_url: await urlToB64(backgroundUrl),
                b64Internal_or_url: await urlToB64(puzzleUrl),
                width: String(width),
                height: String(height),
                version: '2',
                proxy: ''
            };
            break;
        case '3d':
             if (!imageBase64 || !width || !height) {
                throw new Error('For 3d captcha, all params are required.');
            }
            endpoint = '/3d';
            payload = {
                b64External_or_url: imageBase64,
                width: String(width),
                height: String(height),
                version: '2',
                proxy: ''
            };
            break;
        case 'icon':
            if (!imageBase64 || !question || !width || !height) {
                throw new Error('For icon captcha, all params are required.');
            }
            endpoint = '/icon';
            payload = {
                b64External_or_url: imageBase64,
                question: question,
                width: String(width),
                height: String(height),
                version: '2',
                proxy: ''
            };
            break;
        default:
            throw new Error(`Unsupported captcha type: ${captchaType}`);
    }

    const url = `https://${RAPIDAPI_HOST}${endpoint}`;
    console.log(`Sending captcha to ${url} with type ${captchaType}...`);

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'x-rapidapi-host': RAPIDAPI_HOST,
                'x-rapidapi-key': RAPIDAPI_KEY,
                'content-type': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        console.log(response);
        const result = await response.json();

        if (!response.ok || result.errorMsg) {
            const errorDetails = result.errorMsg || await response.text();
            throw new Error(`API request failed with status ${response.status}: ${errorDetails}`);
        }
        
        console.log('Captcha solved successfully:', JSON.stringify(result, null, 2));
        return result;
    } catch (error) {
        console.error('Error solving captcha:', error);
        throw error;
    }
}

module.exports = { solveCaptcha }; 