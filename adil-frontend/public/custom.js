// Custom JavaScript for AskAdil - UK Discrimination Law Assistant
// This script removes any remaining Chainlit branding and applies AskAdil identity

(function () {
    // Override meta tags
    const ogUrl = document.querySelector('meta[property="og:url"]');
    if (ogUrl) ogUrl.setAttribute('content', 'https://askadil.org');

    const ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle) ogTitle.setAttribute('content', 'AskAdil — UK Discrimination Law Assistant');

    const ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc) ogDesc.setAttribute('content', 'Free AI-powered UK discrimination law guidance for British Muslims. Educate First, Litigate Second.');

    // Fix title
    if (document.title.toLowerCase().includes('chainlit')) {
        document.title = "AskAdil — UK Discrimination Law Assistant";
    }

    // Aggressively hide Chainlit branding as soon as DOM elements appear
    function hideChainlitBranding() {
        // Hide any element linking to Chainlit
        document.querySelectorAll('a[href*="chainlit"], a[href*="Chainlit"]').forEach(function(el) {
            el.style.display = 'none';
            // Also hide parent if it's a watermark container
            if (el.parentElement && el.parentElement.children.length === 1) {
                el.parentElement.style.display = 'none';
            }
        });
        // Hide any image with chainlit in src
        document.querySelectorAll('img[src*="chainlit"], img[alt*="chainlit" i]').forEach(function(el) {
            el.style.display = 'none';
        });
        // Fix title if it gets overwritten
        if (document.title.toLowerCase().includes('chainlit')) {
            document.title = "AskAdil — UK Discrimination Law Assistant";
        }
    }

    // Run immediately
    hideChainlitBranding();

    // Watch for DOM changes and hide branding as soon as it appears
    var observer = new MutationObserver(function() {
        hideChainlitBranding();
    });
    observer.observe(document.body || document.documentElement, {
        childList: true,
        subtree: true
    });

    // Stop observing after 10 seconds (page fully loaded by then)
    setTimeout(function() { observer.disconnect(); }, 10000);
})();

