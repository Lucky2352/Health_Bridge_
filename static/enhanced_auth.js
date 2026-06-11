// Enhanced Authentication JavaScript

// Password toggle functionality
function togglePassword(fieldId) {
    const passwordField = document.getElementById(fieldId);
    const toggleIcon = fieldId === 'password' ? 
        document.getElementById('toggleIcon') || document.getElementById('toggleIcon1') :
        document.getElementById('toggleIcon2');
    
    if (passwordField.type === 'password') {
        passwordField.type = 'text';
        toggleIcon.innerHTML = '&#128065;';
    } else {
        passwordField.type = 'password';
        toggleIcon.innerHTML = '&#128065;';
    }
}

// Password strength checker
function checkPasswordStrength() {
    const password = document.getElementById('password').value;
    const strengthFill = document.getElementById('strengthFill');
    const strengthText = document.getElementById('strengthText');
    
    if (!strengthFill || !strengthText) return;
    
    let strength = 0;
    let feedback = '';
    
    // Length check
    if (password.length >= 8) strength += 20;
    if (password.length >= 12) strength += 10;
    
    // Character variety checks
    if (/[a-z]/.test(password)) strength += 20;
    if (/[A-Z]/.test(password)) strength += 20;
    if (/[0-9]/.test(password)) strength += 15;
    if (/[^A-Za-z0-9]/.test(password)) strength += 15;
    
    // Cap at 100
    strength = Math.min(strength, 100);
    
    if (password.length === 0) {
        feedback = 'Enter password';
        strength = 0;
    } else if (strength < 40) {
        feedback = 'Weak password';
        strengthFill.style.background = '#ff6b6b';
    } else if (strength < 70) {
        feedback = 'Good password';
        strengthFill.style.background = '#ffc107';
    } else {
        feedback = 'Strong password';
        strengthFill.style.background = '#51cf66';
    }
    
    strengthFill.style.width = strength + '%';
    strengthText.textContent = feedback;
    
    // Check password match
    checkPasswordMatch();
}

// Password match checker
function checkPasswordMatch() {
    const password = document.getElementById('password');
    const confirmPassword = document.getElementById('confirm_password');
    const matchDiv = document.getElementById('passwordMatch');
    
    if (!password || !confirmPassword || !matchDiv) return;
    
    if (confirmPassword.value === '') {
        matchDiv.textContent = '';
        return;
    }
    
    if (password.value === confirmPassword.value) {
        matchDiv.textContent = '✓ Passwords match';
        matchDiv.style.color = '#51cf66';
    } else {
        matchDiv.textContent = '✗ Passwords do not match';
        matchDiv.style.color = '#ff6b6b';
    }
}

// Enhanced signup form validation
function validateSignupForm() {
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirm_password').value;
    const email = document.getElementById('email').value;
    const fullName = document.getElementById('full_name').value;
    const username = document.getElementById('username').value;
    
    // Clear previous errors
    clearErrors();
    
    let isValid = true;
    
    // Full name validation
    if (!fullName.trim() || fullName.trim().length < 2) {
        showFieldError('full_name', 'Full name must be at least 2 characters');
        isValid = false;
    }
    
    // Email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email.trim() || !emailRegex.test(email)) {
        showFieldError('email', 'Please enter a valid email address');
        isValid = false;
    }
    
    // Username validation
    if (!username.trim() || username.trim().length < 3) {
        showFieldError('username', 'Username must be at least 3 characters');
        isValid = false;
    }
    
    // Password validation
    if (password.length < 8) {
        showFieldError('password', 'Password must be at least 8 characters');
        isValid = false;
    }
    
    // Password strength check
    const strengthScore = calculatePasswordStrength(password);
    if (strengthScore < 40) {
        showFieldError('password', 'Password is too weak');
        isValid = false;
    }
    
    // Password match validation
    if (password !== confirmPassword) {
        showFieldError('confirm_password', 'Passwords do not match');
        isValid = false;
    }
    
    return isValid;
}

// Check username availability
function checkUsernameAvailability(username) {
    const usernameCheck = document.getElementById('username-check');
    
    if (!username || username.length < 3) {
        usernameCheck.textContent = '';
        usernameCheck.className = 'validation-message';
        return;
    }
    
    usernameCheck.textContent = 'Checking availability...';
    usernameCheck.className = 'validation-message checking';
    
    fetch('/enhanced/check-username', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username: username })
    })
    .then(response => response.json())
    .then(data => {
        if (data.available) {
            usernameCheck.textContent = '✓ Username available';
            usernameCheck.className = 'validation-message success';
        } else {
            usernameCheck.textContent = '✗ Username already taken';
            usernameCheck.className = 'validation-message error';
        }
    })
    .catch(error => {
        usernameCheck.textContent = '';
        usernameCheck.className = 'validation-message';
    });
}

// Check email availability
function checkEmailAvailability(email) {
    const emailCheck = document.getElementById('email-check');
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    
    if (!email || !emailRegex.test(email)) {
        emailCheck.textContent = '';
        emailCheck.className = 'validation-message';
        return;
    }
    
    emailCheck.textContent = 'Checking availability...';
    emailCheck.className = 'validation-message checking';
    
    fetch('/enhanced/check-email', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ email: email })
    })
    .then(response => response.json())
    .then(data => {
        if (data.available) {
            emailCheck.textContent = '✓ Email available';
            emailCheck.className = 'validation-message success';
        } else {
            emailCheck.textContent = '✗ Email already registered';
            emailCheck.className = 'validation-message error';
        }
    })
    .catch(error => {
        emailCheck.textContent = '';
        emailCheck.className = 'validation-message';
    });
}

// Calculate password strength score
function calculatePasswordStrength(password) {
    let strength = 0;
    
    if (password.length >= 8) strength += 20;
    if (password.length >= 12) strength += 10;
    if (/[a-z]/.test(password)) strength += 20;
    if (/[A-Z]/.test(password)) strength += 20;
    if (/[0-9]/.test(password)) strength += 15;
    if (/[^A-Za-z0-9]/.test(password)) strength += 15;
    
    return Math.min(strength, 100);
}

// Show field-specific error
function showFieldError(fieldId, message) {
    const field = document.getElementById(fieldId);
    if (field) {
        field.style.borderColor = '#ff6b6b';
        
        // Create or update error message
        let errorDiv = field.parentNode.querySelector('.field-error');
        if (!errorDiv) {
            errorDiv = document.createElement('div');
            errorDiv.className = 'field-error';
            errorDiv.style.cssText = 'color: #ff6b6b; font-size: 0.8rem; margin-top: 0.25rem;';
            field.parentNode.appendChild(errorDiv);
        }
        errorDiv.textContent = message;
    }
}

// Clear all field errors
function clearErrors() {
    const errorDivs = document.querySelectorAll('.field-error');
    errorDivs.forEach(div => div.remove());
    
    const fields = document.querySelectorAll('input');
    fields.forEach(field => {
        field.style.borderColor = 'rgba(255, 255, 255, 0.1)';
    });
}

// Enhanced alert system
function showAlert(message, type = 'info') {
    // Remove existing alerts
    const existingAlert = document.querySelector('.alert');
    if (existingAlert) {
        existingAlert.remove();
    }
    
    // Create new alert
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" style="background: none; border: none; color: inherit; float: right; cursor: pointer;">&times;</button>
    `;
    
    // Insert after form title
    const form = document.querySelector('.form');
    if (form) {
        form.parentNode.insertBefore(alert, form);
    }
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (alert.parentNode) {
            alert.remove();
        }
    }, 5000);
}

// Remember me functionality
function toggleRememberMe() {
    const checkbox = document.getElementById('remember_me');
    const label = checkbox.nextElementSibling;
    
    if (checkbox.checked) {
        showAlert('You will stay signed in for 30 days', 'success');
    }
}

// Google Sign-In setup info
function showGoogleSetupInfo() {
    window.location.href = '/enhanced/google-login';
}

// Google Sign-In handler (for when configured)
function handleGoogleSignIn() {
    window.location.href = '/enhanced/google-login';
}

// Role-based dashboard features
function initializeDashboard() {
    // Add interactive features based on user role
    const roleElements = document.querySelectorAll('[data-role]');
    
    roleElements.forEach(element => {
        const requiredRole = element.getAttribute('data-role');
        const userRole = getCurrentUserRole();
        
        if (!hasPermission(userRole, requiredRole)) {
            element.style.display = 'none';
        }
    });
}

// Check user permissions
function hasPermission(userRole, requiredRole) {
    const roleHierarchy = {
        'admin': ['admin', 'doctor', 'patient'],
        'doctor': ['doctor', 'patient'],
        'patient': ['patient']
    };
    
    return roleHierarchy[userRole]?.includes(requiredRole) || false;
}

// Get current user role (would be set by server)
function getCurrentUserRole() {
    // This would be populated by the server template
    return window.currentUserRole || 'patient';
}

// Event listeners
document.addEventListener('DOMContentLoaded', function() {
    // Password match checking
    const confirmPassword = document.getElementById('confirm_password');
    if (confirmPassword) {
        confirmPassword.addEventListener('input', checkPasswordMatch);
    }
    
    // Real-time email validation and availability check
    const emailField = document.getElementById('email');
    if (emailField) {
        let emailTimeout;
        emailField.addEventListener('input', function() {
            clearTimeout(emailTimeout);
            emailTimeout = setTimeout(() => {
                checkEmailAvailability(this.value.trim());
            }, 500);
        });
        
        emailField.addEventListener('blur', function() {
            const email = this.value.trim();
            if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
                showFieldError('email', 'Please enter a valid email address');
            } else {
                clearFieldError('email');
            }
        });
    }
    
    // Real-time username validation and availability check
    const usernameField = document.getElementById('username');
    if (usernameField) {
        let usernameTimeout;
        usernameField.addEventListener('input', function() {
            clearTimeout(usernameTimeout);
            usernameTimeout = setTimeout(() => {
                checkUsernameAvailability(this.value.trim());
            }, 500);
        });
    }
    
    // Remember me checkbox
    const rememberCheckbox = document.getElementById('remember_me');
    if (rememberCheckbox) {
        rememberCheckbox.addEventListener('change', toggleRememberMe);
    }
    
    // Initialize dashboard features
    initializeDashboard();
    
    // Form submission handling
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (this.onsubmit && typeof this.onsubmit === 'function') {
                if (!this.onsubmit()) {
                    e.preventDefault();
                }
            }
        });
    });
});

// Clear specific field error
function clearFieldError(fieldId) {
    const field = document.getElementById(fieldId);
    if (field) {
        field.style.borderColor = 'rgba(255, 255, 255, 0.1)';
        const errorDiv = field.parentNode.querySelector('.field-error');
        if (errorDiv) {
            errorDiv.remove();
        }
    }
}

// Session management
function extendSession() {
    // Keep session alive for remember me functionality
    fetch('/enhanced/extend-session', {
        method: 'POST',
        credentials: 'same-origin'
    }).catch(err => console.log('Session extension failed'));
}

// Auto-extend session every 15 minutes if remember me is enabled
if (localStorage.getItem('rememberMe') === 'true') {
    setInterval(extendSession, 15 * 60 * 1000);
}