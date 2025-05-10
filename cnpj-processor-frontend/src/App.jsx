import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Navbar from './components/Navbar';
import HomePage from './pages/HomePage';
import UploadPage from './pages/UploadPage';
import ConsultaPage from './pages/ConsultaPage';
import CertidaoPage from './pages/CertidaoPage';
import LoginPage from './pages/LoginPage';
import ProtectedRoute from './components/ProtectedRoute';
import { initializeAuth } from './services/auth';
import './App.css';

// Wrapper component that always renders the Navbar for authenticated routes
const AppContent = () => {
  const location = useLocation();
  const isLoginPage = location.pathname === '/login';
  
  return (
    <div className="app">
      {!isLoginPage && <Navbar />}
      <main className={`content ${isLoginPage ? 'full-height' : ''}`}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          
          {/* Protected routes */}
          <Route path="/" element={
            <ProtectedRoute>
              <HomePage />
            </ProtectedRoute>
          } />
          <Route path="/upload" element={
            <ProtectedRoute>
              <UploadPage />
            </ProtectedRoute>
          } />
          <Route path="/consulta" element={
            <ProtectedRoute>
              <ConsultaPage />
            </ProtectedRoute>
          } />
          <Route path="/certidao/:id" element={
            <ProtectedRoute>
              <CertidaoPage />
            </ProtectedRoute>
          } />
        </Routes>
      </main>
    </div>
  );
};

function App() {
  // Initialize authentication on app load
  useEffect(() => {
    initializeAuth();
  }, []);

  return (
    <Router>
      <AppContent />
    </Router>
  );
}

export default App;
