const { solveCaptcha } = require('./captcha_solver');

(async () => {
    const base64Image = process.argv[2];
    if (!base64Image) {
        console.error(JSON.stringify({ success: false, error: 'No image provided' }));
        process.exit(1);
    }

    try {
        const result = await solveCaptcha({
            captchaType: '3d',
            imageBase64: base64Image
        });
        console.log(JSON.stringify(result));
    } catch (error) {
        console.error(JSON.stringify({ success: false, error: error.message }));
        process.exit(1);
    }
})(); 