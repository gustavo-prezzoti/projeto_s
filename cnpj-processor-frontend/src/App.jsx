import React from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Navbar from './components/Navbar';
import HomePage from './pages/HomePage';
import UploadPage from './pages/UploadPage';
import ConsultaPage from './pages/ConsultaPage';
import CertidaoPage from './pages/CertidaoPage';
import './App.css';

// Wrapper component that conditionally renders the Navbar
const AppContent = () => {
  const location = useLocation();
  const isCertidaoPage = location.pathname.includes('/certidao/');
  
  return (
    <div className="app">
      {!isCertidaoPage && <Navbar />}
      <main className="content">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/consulta" element={<ConsultaPage />} />
          <Route path="/certidao/:id" element={<CertidaoPage />} />
        </Routes>
      </main>
    </div>
  );
};

function App() {
  return (
    <Router>
      <AppContent />
    </Router>
  );
}

export default App;
