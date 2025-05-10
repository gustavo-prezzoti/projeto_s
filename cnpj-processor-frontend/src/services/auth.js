import axios from 'axios';

const TOKEN_KEY = 'cnpj_processor_token';
const USER_KEY = 'cnpj_processor_user';

// Create axios instance for auth requests
const authApi = axios.create({
  baseURL: '/api',
});

// Login function
export const login = async (username, password) => {
  try {
    const response = await authApi.post('/auth/token', {
      username,
      password
    });
    
    const { access_token, token_type, user_id, username: userName } = response.data;
    
    // Store token and user data
    localStorage.setItem(TOKEN_KEY, access_token);
    localStorage.setItem(USER_KEY, JSON.stringify({
      id: user_id,
      username: userName
    }));
    
    // Set token for all future requests
    setAuthHeader(access_token);
    
    return true;
  } catch (error) {
    console.error('Login error:', error);
    
    // Handle 401 specifically as invalid credentials
    if (error.response && error.response.status === 401) {
      return false;
    }
    
    // Re-throw for other errors
    throw error;
  }
};

// Logout function
export const logout = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  removeAuthHeader();
};

// Check if user is authenticated
export const isAuthenticated = () => {
  return localStorage.getItem(TOKEN_KEY) !== null;
};

// Get current user
export const getCurrentUser = () => {
  const userStr = localStorage.getItem(USER_KEY);
  if (!userStr) return null;
  
  try {
    return JSON.parse(userStr);
  } catch (e) {
    console.error('Error parsing user data', e);
    return null;
  }
};

// Get token
export const getToken = () => {
  return localStorage.getItem(TOKEN_KEY);
};

// Set auth header for API requests
export const setAuthHeader = (token) => {
  if (token) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }
};

// Remove auth header
export const removeAuthHeader = () => {
  delete axios.defaults.headers.common['Authorization'];
};

// Initialize auth header from storage on app load
export const initializeAuth = () => {
  const token = getToken();
  if (token) {
    setAuthHeader(token);
    return true;
  }
  return false;
};

export default {
  login,
  logout,
  isAuthenticated,
  getCurrentUser,
  getToken,
  initializeAuth
}; 