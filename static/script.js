// Инициализация Telegram Web App
let tg = window.Telegram.WebApp;

// DOM элементы
const favoritesList = document.getElementById('favoritesList');

// Функция загрузки избранного
async function loadFavorites(chatId) {
    showLoading(favoritesList);
    try {
        const response = await fetch(`/app/favorites?chat_id=${chatId}`);
        const data = await response.json();
        
        if (data.favorites) {
            displayFavorites(data.favorites, favoritesList);
        } else {
            showError(favoritesList, 'Ошибка загрузки избранного: ' + (data.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        console.error('Ошибка:', error);
        showError(favoritesList, 'Ошибка загрузки данных: ' + error.message);
    }
}

function showLoading(container) {
    container.innerHTML = '<div class="loading">Загрузка избранного...</div>';
}

function showError(container, message) {
    container.innerHTML = `<div class="error">${message}</div>`;
}

function displayFavorites(favorites, container) {
    if (favorites.length === 0) {
        container.innerHTML = '<div class="error">Избранных роз нет</div>';
        return;
    }
    
    container.innerHTML = favorites.map(rose => `
        <div class="rose-card">
            ${rose.photo ? `<img src="${rose.photo}" alt="${rose.name}" class="rose-image" onerror="this.style.display='none'">` : ''}
            <div class="rose-info">
                <h3 class="rose-name">${rose.name}</h3>
                <p class="rose-description">${truncateText(rose.description, 100)}</p>
            </div>
        </div>
    `).join('');
}

function truncateText(text, maxLength) {
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

// Обработчик события загрузки страницы
document.addEventListener('DOMContentLoaded', function() {
    // Получаем ID чата из Telegram Web App
    const tg = window.Telegram.WebApp;
    if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
        const chatId = tg.initDataUnsafe.user.id;
        loadFavorites(chatId);
    } else {
        // Если не удалось получить из initData, попробуем из URL
        const urlParams = new URLSearchParams(window.location.search);
        const chatId = urlParams.get('chat_id');
        if (chatId) {
            loadFavorites(chatId);
        } else {
            document.getElementById('favoritesList').innerHTML = 
                '<div class="error">Не удалось получить данные пользователя</div>';
        }
    }
});
