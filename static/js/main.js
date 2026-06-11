// Mobile menu toggle
function toggleMobileMenu() {
    const sidebar = document.querySelector('.dashboard-sidebar');
    sidebar.classList.toggle('mobile-open');
}

// Notification system
function showNotification(message, type) {
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 1rem 1.5rem;
        border-radius: 12px;
        color: white;
        font-weight: 500;
        z-index: 1000;
        animation: slideIn 0.3s ease-out;
        ${type === 'error' ? 
            'background: rgba(255, 107, 107, 0.9); border: 1px solid #ff6b6b;' : 
            'background: rgba(81, 207, 102, 0.9); border: 1px solid #51cf66;'
        }
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Add slide-in animation styles
document.addEventListener('DOMContentLoaded', function() {
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
    `;
    document.head.appendChild(style);
});