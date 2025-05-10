import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FiUpload, FiCheckCircle, FiAlertCircle, FiRefreshCw } from 'react-icons/fi';
import { uploadExcel } from '../services/api';
import './HomePage.css';

const HomePage = () => {
  const [isDragging, setIsDragging] = useState(false);
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    
    const droppedFile = e.dataTransfer.files[0];
    handleFileSelection(droppedFile);
  };

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    handleFileSelection(selectedFile);
  };

  const handleFileSelection = (selectedFile) => {
    // Limpar mensagens anteriores
    setError(null);
    setMessage(null);
    
    if (!selectedFile) {
      return;
    }
    
    // Verificar se é um arquivo Excel
    const isExcelFile = selectedFile.name.endsWith('.xlsx') || selectedFile.name.endsWith('.xls');
    if (!isExcelFile) {
      setFile(null);
      setError('Por favor, selecione um arquivo Excel (.xlsx ou .xls)');
      return;
    }
    
    // Verificar tamanho do arquivo (limite de 10MB)
    const maxSize = 10 * 1024 * 1024; // 10MB em bytes
    if (selectedFile.size > maxSize) {
      setFile(null);
      setError(`O arquivo é muito grande (${(selectedFile.size / (1024 * 1024)).toFixed(2)}MB). O tamanho máximo é 10MB.`);
      return;
    }
    
    // Arquivo válido
    setFile(selectedFile);
    setMessage(`Arquivo "${selectedFile.name}" selecionado com sucesso (${(selectedFile.size / 1024).toFixed(2)}KB)`);
  };

  const handleUpload = async () => {
    if (!file) {
      setError('Por favor, selecione um arquivo Excel para processar');
      return;
    }
    
    setLoading(true);
    setError(null);
    setMessage('Enviando arquivo para processamento...');
    
    try {
      const result = await uploadExcel(file);
      
      if (result && result.total_processed) {
        setMessage(`${result.total_processed} CNPJs foram enviados para processamento!`);
        setFile(null);
        
        // Limpar input file se existir
        const fileInput = document.getElementById('fileInput');
        if (fileInput) fileInput.value = '';
        
        // Redirecionar para a página de consulta imediatamente
        navigate('/consulta');
      } else {
        setError('Nenhum CNPJ foi encontrado no arquivo. Verifique se o formato está correto.');
      }
    } catch (err) {
      console.error('Erro completo:', err);
      // Exibir mensagem de erro mais detalhada
      const errorMessage = err.response?.data?.detail 
        || err.message 
        || 'Erro desconhecido ao processar o arquivo';
      setError(`Erro: ${errorMessage}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="home-container">
      <div className="hero-section">
        <h1>Sistema de Processamento de CNPJ</h1>
      </div>
      
      <div 
        className={`upload-area ${isDragging ? 'dragging' : ''}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <div className="upload-icon-large">
          <FiUpload />
        </div>
        <h2 className="upload-title">Arraste seu arquivo Excel aqui</h2>
        <p>ou</p>
        <label htmlFor="fileInput" className="select-file-btn">
          Selecionar arquivo
        </label>
        <input 
          type="file" 
          id="fileInput"
          accept=".xlsx,.xls"
          onChange={handleFileChange}
          className="file-input" 
        />
        
        {file && (
          <div className="selected-file">
            <p>Arquivo selecionado: <strong>{file.name}</strong></p>
            <p className="file-size">Tamanho: {(file.size / 1024).toFixed(2)} KB</p>
            <button 
              className="process-btn"
              onClick={handleUpload}
              disabled={loading}
            >
              {loading ? (
                <>
                  <FiRefreshCw className="spinning" style={{ marginRight: '8px' }} /> 
                  Processando...
                </>
              ) : (
                'Processar arquivo'
              )}
            </button>
          </div>
        )}
        
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
    </div>
  );
};

export default HomePage; 