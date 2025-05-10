import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { FiList, FiHome, FiLogOut } from 'react-icons/fi';
import { logout } from '../services/auth';
import './Navbar.css';

const Navbar = () => {
  const location = useLocation();
  const navigate = useNavigate();
  
  // No longer hiding navbar on certificate pages
  
  const isActive = (path) => {
    return location.pathname === path ? 'active' : '';
  };
  
  const handleLogout = () => {
    logout();
    navigate('/login');
  };
  
  return (
    <nav className="navbar">
      <div className="navbar-brand">
        <h1>CNPJ Processor</h1>
      </div>
      
      <ul className="navbar-nav">
        <li className="nav-item">
          <Link to="/" className={`nav-link ${isActive('/')}`}>
            <FiHome />
            <span>Início</span>
          </Link>
        </li>
        <li className="nav-item">
          <Link to="/consulta" className={`nav-link ${isActive('/consulta')}`}>
            <FiList />
            <span>Consulta CNPJs</span>
          </Link>
        </li>
        <li className="nav-item">
          <button onClick={handleLogout} className="nav-link logout-button">
            <FiLogOut />
            <span>Sair</span>
          </button>
        </li>
      </ul>
    </nav>
  );
};

export default Navbar; 