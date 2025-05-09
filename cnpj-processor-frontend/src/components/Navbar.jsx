import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { FiList, FiHome } from 'react-icons/fi';
import './Navbar.css';

const Navbar = () => {
  const location = useLocation();
  
  // Hide navbar on certificate pages
  if (location.pathname.includes('/certidao/')) {
    return null;
  }
  
  const isActive = (path) => {
    return location.pathname === path ? 'active' : '';
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
      </ul>
    </nav>
  );
};

export default Navbar; 