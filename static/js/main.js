// Main JavaScript for Session-Based Recommendation System

// Global variables
let socket = null;
let isConnected = false;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeSocket();
    initializeTooltips();
    initializeFormValidation();
});

// Initialize Socket.IO connection
function initializeSocket() {
    if (typeof io !== 'undefined') {
        socket = io();
        
        socket.on('connect', function() {
            isConnected = true;
            console.log('Connected to server');
            updateConnectionStatus(true);
        });
        
        socket.on('disconnect', function() {
            isConnected = false;
            console.log('Disconnected from server');
            updateConnectionStatus(false);
        });
        
        socket.on('error', function(error) {
            console.error('Socket error:', error);
            showNotification('Connection error: ' + error.message, 'error');
        });
    }
}

// Update connection status indicator
function updateConnectionStatus(connected) {
    const statusElements = document.querySelectorAll('.connection-status');
    statusElements.forEach(element => {
        element.textContent = connected ? 'Connected' : 'Disconnected';
        element.className = connected ? 'connection-status text-success' : 'connection-status text-danger';
    });
}

// Initialize Bootstrap tooltips
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Initialize form validation
function initializeFormValidation() {
    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(form => {
        form.addEventListener('submit', event => {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });
}

// Show notification
function showNotification(message, type = 'info') {
    const alertClass = {
        'success': 'alert-success',
        'error': 'alert-danger',
        'warning': 'alert-warning',
        'info': 'alert-info'
    }[type] || 'alert-info';
    
    const notification = document.createElement('div');
    notification.className = `alert ${alertClass} alert-dismissible fade show position-fixed`;
    notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (notification.parentNode) {
            notification.remove();
        }
    }, 5000);
}

// Loading state management
function setLoading(element, loading = true) {
    if (loading) {
        element.classList.add('loading');
        const spinner = element.querySelector('.spinner') || createSpinner();
        if (!element.querySelector('.spinner')) {
            element.appendChild(spinner);
        }
    } else {
        element.classList.remove('loading');
        const spinner = element.querySelector('.spinner');
        if (spinner) {
            spinner.remove();
        }
    }
}

// Create spinner element
function createSpinner() {
    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    return spinner;
}

// Format numbers
function formatNumber(num) {
    return new Intl.NumberFormat().format(num);
}

// Format time
function formatTime(timestamp) {
    return new Date(timestamp).toLocaleTimeString();
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showNotification('Copied to clipboard!', 'success');
    }).catch(err => {
        console.error('Failed to copy: ', err);
        showNotification('Failed to copy to clipboard', 'error');
    });
}

// Smooth scroll to element
function scrollToElement(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.scrollIntoView({ behavior: 'smooth' });
    }
}

// API helper functions
async function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
    };
    
    const config = { ...defaultOptions, ...options };
    
    try {
        const response = await fetch(url, config);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('API request failed:', error);
        showNotification('Request failed: ' + error.message, 'error');
        throw error;
    }
}

// Graph visualization helpers
function createGraphOptions() {
    return {
        nodes: {
            shape: 'dot',
            size: 20,
            font: { size: 12, color: '#000000' },
            borderWidth: 2,
            shadow: true,
            scaling: {
                min: 10,
                max: 30,
                label: {
                    min: 8,
                    max: 20,
                    drawThreshold: 12,
                    maxVisible: 20
                }
            }
        },
        edges: {
            width: 2,
            color: { inherit: 'from' },
            smooth: { type: 'continuous' },
            scaling: {
                min: 1,
                max: 10
            }
        },
        physics: {
            stabilization: { iterations: 100 },
            barnesHut: {
                gravitationalConstant: -2000,
                centralGravity: 0.3,
                springLength: 95,
                springConstant: 0.04,
                damping: 0.09
            }
        },
        interaction: {
            hover: true,
            tooltipDelay: 200,
            hideEdgesOnDrag: true
        }
    };
}

// Export functions for global use
window.RecommendationApp = {
    showNotification,
    setLoading,
    formatNumber,
    formatTime,
    copyToClipboard,
    scrollToElement,
    apiRequest,
    createGraphOptions,
    socket: () => socket,
    isConnected: () => isConnected
};
