import React, { useState } from 'react';
import { uploadExcel } from '../services/api';
import { FiUpload, FiCheckCircle, FiAlertCircle } from 'react-icons/fi';
import './UploadPage.css';

const UploadPage = () => {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    
    if (selectedFile) {
      // Verificar se é um arquivo Excel
      if (selectedFile.name.endsWith('.xlsx') || selectedFile.name.endsWith('.xls')) {
        setFile(selectedFile);
        setError(null);
      } else {
        setFile(null);
        setError('Por favor, selecione um arquivo Excel (.xlsx ou .xls)');
      }
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!file) {
      setError('Por favor, selecione um arquivo Excel para processar');
      return;
    }
    
    setLoading(true);
    setError(null);
    setMessage(null);
    
    try {
      const result = await uploadExcel(file);
      setMessage(`${result.total_processed} CNPJs foram enviados para processamento!`);
      setFile(null);
      // Limpar o input file
      document.getElementById('fileInput').value = '';
    } catch (err) {
      setError(err.response?.data?.detail || 'Erro ao processar o arquivo');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="upload-container">
      <h1>Upload de Arquivo Excel</h1>
      <p className="instructions">
        Faça upload de um arquivo Excel contendo dados de CNPJs para processamento.
      </p>
      
      <form onSubmit={handleSubmit} className="upload-form">
        <div className="file-input-container">
          <label htmlFor="fileInput" className="file-input-label">
            <FiUpload className="upload-icon" />
            {file ? file.name : 'Escolher arquivo Excel'}
          </label>
          <input
            type="file"
            id="fileInput"
            accept=".xlsx,.xls"
            onChange={handleFileChange}
            className="file-input"
          />
        </div>
        
        <button 
          type="submit" 
          className="upload-button"
          disabled={loading || !file}
        >
          {loading ? 'Processando...' : 'Enviar para processamento'}
        </button>
      </form>
      
      {message && (
        <div className="message success">
          <FiCheckCircle className="message-icon" />
          {message}
        </div>
      )}
      
      {error && (
        <div className="message error">
          <FiAlertCircle className="message-icon" />
          {error}
        </div>
      )}
    </div>
  );
};

export default UploadPage; 