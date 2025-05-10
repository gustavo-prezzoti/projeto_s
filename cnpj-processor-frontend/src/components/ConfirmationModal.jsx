import React from 'react';
import { FiAlertTriangle, FiX, FiTrash2 } from 'react-icons/fi';
import './ConfirmationModal.css';

const ConfirmationModal = ({ 
  isOpen, 
  title, 
  message, 
  confirmText, 
  cancelText, 
  onConfirm, 
  onCancel, 
  isLoading 
}) => {
  if (!isOpen) return null;

  return (
    <div className="confirmation-modal-overlay" onClick={onCancel}>
      <div className="confirmation-modal" onClick={(e) => e.stopPropagation()}>
        <button className="close-button" onClick={onCancel} aria-label="Fechar">
          <FiX />
        </button>
        
        <div className="confirmation-content">
          <div className="confirmation-icon">
            <FiAlertTriangle />
          </div>
          
          <h2 className="confirmation-title">{title}</h2>
          <p className="confirmation-message">{message}</p>
        </div>
        
        <div className="confirmation-actions">
          <button 
            className="btn-cancel" 
            onClick={onCancel}
            disabled={isLoading}
          >
            {cancelText || 'Cancelar'}
          </button>
          
          <button 
            className="btn-confirm" 
            onClick={onConfirm}
            disabled={isLoading}
          >
            {isLoading ? (
              <span className="loading-spinner"></span>
            ) : (
              <>
                <FiTrash2 /> {confirmText || 'Confirmar'}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmationModal; 