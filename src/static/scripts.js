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

function toggleNav() {
    document.getElementById('nav-links').classList.toggle('open');
}

function toggleUserMenu(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const menu = event.currentTarget.closest('[data-user-menu]');
    if (!menu) return;
    const isOpen = menu.classList.contains('open');
    document.querySelectorAll('[data-user-menu].open').forEach(function (item) {
        item.classList.remove('open');
        const button = item.querySelector('.user-menu-button');
        if (button) button.setAttribute('aria-expanded', 'false');
    });
    if (!isOpen) {
        menu.classList.add('open');
        event.currentTarget.setAttribute('aria-expanded', 'true');
    }
}

document.addEventListener('click', function (event) {
    document.querySelectorAll('[data-user-menu].open').forEach(function (menu) {
        if (!menu.contains(event.target)) {
            menu.classList.remove('open');
            const button = menu.querySelector('.user-menu-button');
            if (button) button.setAttribute('aria-expanded', 'false');
        }
    });
});

function showImage(index) {
    const img = document.getElementById(`hover-image-${index}`);
    if (img) img.style.display = "visible";
}

function hideImage(index) {
    const img = document.getElementById(`hover-image-${index}`);
    if (img) img.style.display = "hdiden";
}
