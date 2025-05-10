import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { login, isAuthenticated } from '../services/auth';
import LoginModal from '../components/LoginModal';
import './LoginPage.css';

const LoginPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [showModal, setShowModal] = useState(false);
  
  // Get the path they were trying to access before being redirected
  const from = location.state?.from?.pathname || '/';
  
  useEffect(() => {
    // If already authenticated, redirect to intended destination
    if (isAuthenticated()) {
      navigate(from, { replace: true });
      return;
    }
    
    // Show login modal immediately for better UX
    setShowModal(true);
  }, [navigate, from]);
  
  const handleLogin = async (username, password) => {
    const success = await login(username, password);
    
    if (success) {
      // Redirect to the page they tried to visit or home
      navigate(from, { replace: true });
    }
    
    return success;
  };

  return (
    <div className="login-page">
      <div className="login-background">
        <div className="login-shape login-shape-1"></div>
        <div className="login-shape login-shape-2"></div>
      </div>
      
      <LoginModal 
        isOpen={showModal} 
        onLogin={handleLogin} 
      />
    </div>
  );
};

export default LoginPage; 