// Custom JavaScript for AskAdil - UK Discrimination Law Assistant
// This script removes any remaining Chainlit branding and applies AskAdil identity

(function () {
    // Override og:url meta tag
    const ogUrl = document.querySelector('meta[property="og:url"]');
    if (ogUrl) {
        ogUrl.setAttribute('content', 'https://askadil.org');
    }

    // Ensure title is correct
    if (document.title.toLowerCase().includes('chainlit')) {
        document.title = "AskAdil — UK Discrimination Law Assistant";
    }

    // Override og:title meta tag
    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle) {
        ogTitle.setAttribute('content', 'AskAdil — UK Discrimination Law Assistant');
    }

    // Override og:description meta tag
    const ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc) {
        ogDesc.setAttribute('content', 'Free AI-powered UK discrimination law guidance for British Muslims. Educate First, Litigate Second.');
    }
})();

