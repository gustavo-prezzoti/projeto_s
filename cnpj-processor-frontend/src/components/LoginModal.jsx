import React, { useState, useEffect } from 'react';
import { FiUser, FiLock, FiAlertCircle, FiEye, FiEyeOff } from 'react-icons/fi';
import './LoginModal.css';

const LoginModal = ({ onLogin, isOpen }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Clear form on open
  useEffect(() => {
    if (isOpen) {
      setUsername('');
      setPassword('');
      setError('');
      setShowPassword(false);
    }
  }, [isOpen]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!username.trim() || !password.trim()) {
      setError('Por favor, preencha todos os campos.');
      return;
    }
    
    setLoading(true);
    setError('');
    
    try {
      const success = await onLogin(username, password);
      if (!success) {
        setError('Credenciais inválidas. Por favor, tente novamente.');
      }
    } catch (err) {
      setError(err.message || 'Ocorreu um erro durante o login. Por favor, tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  const toggleShowPassword = () => {
    setShowPassword(!showPassword);
  };

  if (!isOpen) return null;

  return (
    <div className="login-modal-overlay">
      <div className="login-modal">
        <div className="login-header">
          <h2 className="login-title">CNPJ Processor</h2>
          <p>Faça login para continuar</p>
        </div>
        
        <form onSubmit={handleSubmit} className="login-form">
          {error && (
            <div className="login-error">
              <FiAlertCircle />
              <span>{error}</span>
            </div>
          )}
          
          <div className="form-group">
            <FiUser className="input-icon" />
            <input
              type="text"
              placeholder="Digite seu usuário"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              autoComplete="username"
              autoFocus
            />
          </div>
          
          <div className="form-group">
            <FiLock className="input-icon" />
            <input
              type={showPassword ? "text" : "password"}
              placeholder="Digite sua senha"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              autoComplete="current-password"
            />
            <button 
              type="button" 
              className="password-toggle"
              onClick={toggleShowPassword}
              aria-label={showPassword ? "Esconder senha" : "Mostrar senha"}
            >
              {showPassword ? <FiEyeOff /> : <FiEye />}
            </button>
          </div>
          
          <button type="submit" className="login-button" disabled={loading}>
            {loading ? <span className="loading-spinner"></span> : 'Entrar'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default LoginModal; 