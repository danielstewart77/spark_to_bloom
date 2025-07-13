document.addEventListener('DOMContentLoaded', function () {
    //updateWelcomeMessage();
    updateFooterQuote();
});

// function updateWelcomeMessage() {
//     const hour = new Date().getHours();
//     const welcomeText = document.querySelector('main p');
//     if (hour < 12) {
//         welcomeText.textContent = 'Good Morning! Welcome to Spark to Bloom.';
//     } else if (hour < 18) {
//         welcomeText.textContent = 'Good Afternoon! Welcome to Spark to Bloom.';
//     } else {
//         welcomeText.textContent = 'Good Evening! Welcome to Spark to Bloom.';
//     }
// }

function updateFooterQuote() {
    const quotes = [
        "> grow, one step at a time.",
        "> every day is a new opportunity to grow.",
        "> bloom where you are planted.",
    ];
    const quote = quotes[new Date().getDate() % quotes.length];
    document.querySelector('footer p').textContent = quote;
}

function showImage(index) {
    const img = document.getElementById(`hover-image-${index}`);
    if (img) img.style.display = "visible";
}

function hideImage(index) {
    const img = document.getElementById(`hover-image-${index}`);
    if (img) img.style.display = "hdiden";
}
