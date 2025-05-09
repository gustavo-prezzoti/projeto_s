import React, { useState, useEffect, useRef } from 'react';
import { consultarCnpjs, reprocessarErros, reprocessarCnpjIndividual } from '../services/api';
import { FiRefreshCw, FiFilter, FiX, FiSearch, FiAlertCircle, FiCheckCircle, FiFileText, FiChevronDown } from 'react-icons/fi';
import './ConsultaPage.css';

const ConsultaPage = () => {
  const [cnpjs, setCnpjs] = useState([]);
  const [stats, setStats] = useState({
    total: 0,
    pendentes: 0,
    processando: 0,
    concluidos: 0,
    erros: 0
  });
  const [loading, setLoading] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [filters, setFilters] = useState({
    status: '',
    textoErro: ''
  });
  const [autoRefresh, setAutoRefresh] = useState(true);
  const autoRefreshIntervalRef = useRef(null);
  const itemsPerPage = 10;
  const [batchReprocessConfig, setBatchReprocessConfig] = useState({
    showOptions: false,
    limite: 100
  });

  useEffect(() => {
    // Carregar CNPJs na inicialização
    loadCnpjs();
    
    // Configurar intervalo de atualização automática
    if (autoRefresh) {
      autoRefreshIntervalRef.current = setInterval(() => {
        // Atualizar silenciosamente sem mostrar o indicador de carregamento
        refreshCnpjsSilently();
      }, 5000); // 5 segundos
    }
    
    // Cleanup na desmontagem do componente
    return () => {
      if (autoRefreshIntervalRef.current) {
        clearInterval(autoRefreshIntervalRef.current);
      }
    };
  }, [filters, currentPage, autoRefresh]);

  // Atualização silenciosa sem mostrar indicador de carregamento
  const refreshCnpjsSilently = async () => {
    try {
      const filterParams = {
        ...filters,
      };
      
      // Remover parâmetros vazios
      Object.keys(filterParams).forEach(key => 
        !filterParams[key] && delete filterParams[key]
      );
      
      const data = await consultarCnpjs(filterParams);
      setCnpjs(data.cnpjs || []);
      setStats({
        total: data.total || 0,
        pendentes: data.pendentes || 0,
        processando: data.processando || 0,
        concluidos: data.concluidos || 0,
        erros: data.erros || 0
      });
    } catch (err) {
      console.error('Erro na atualização automática:', err);
      // Não mostrar erro para o usuário em atualizações silenciosas
    }
  };

  const loadCnpjs = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const filterParams = {
        ...filters,
        // Adicionar paginação no backend quando implementado
      };
      
      // Remover parâmetros vazios
      Object.keys(filterParams).forEach(key => 
        !filterParams[key] && delete filterParams[key]
      );
      
      const data = await consultarCnpjs(filterParams);
      setCnpjs(data.cnpjs || []);
      setStats({
        total: data.total || 0,
        pendentes: data.pendentes || 0,
        processando: data.processando || 0,
        concluidos: data.concluidos || 0,
        erros: data.erros || 0
      });
    } catch (err) {
      setError('Erro ao carregar CNPJs: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const handleFilterChange = (e) => {
    const { name, value } = e.target;
    setFilters(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const applyFilters = (e) => {
    e.preventDefault();
    setCurrentPage(1);
    loadCnpjs();
  };

  const clearFilters = () => {
    setFilters({
      status: '',
      textoErro: ''
    });
    setCurrentPage(1);
    // Chamar loadCnpjs após limpar os filtros
    setTimeout(loadCnpjs, 0);
  };
  
  const toggleAutoRefresh = () => {
    // Se estiver desligando o auto-refresh, limpar o intervalo
    if (autoRefresh && autoRefreshIntervalRef.current) {
      clearInterval(autoRefreshIntervalRef.current);
      autoRefreshIntervalRef.current = null;
    }
    
    // Alternar estado
    setAutoRefresh(!autoRefresh);
  };

  const handleReprocessAll = async (customOptions = {}) => {
    if (stats.erros === 0) {
      setError('Não há CNPJs com erro para reprocessar');
      return;
    }

    setReprocessing(true);
    setError(null);
    setMessage(null);
    
    try {
      // Se houver filtro de texto de erro, passar para a API
      const textoErro = filters.textoErro || null;
      // Use provided options or defaults from state
      const limite = customOptions.limite || batchReprocessConfig.limite;
      
      const result = await reprocessarErros(textoErro, null, limite);
      setMessage(`${result.total_processed} CNPJs foram enviados para reprocessamento!`);
      
      // Recarregar dados após reprocessamento
      loadCnpjs();
    } catch (err) {
      setError('Erro ao reprocessar CNPJs: ' + (err.response?.data?.detail || err.message));
    } finally {
      setReprocessing(false);
      // Close options after processing
      setBatchReprocessConfig(prev => ({...prev, showOptions: false}));
    }
  };

  const handleReprocessOne = async (id, cnpj) => {
    setReprocessing(true);
    setError(null);
    setMessage(null);
    
    try {
      // Use the dedicated API for individual CNPJ reprocessing
      await reprocessarCnpjIndividual(id, false);
      setMessage(`CNPJ ${cnpj} enviado para reprocessamento!`);
      
      // Recarregar dados após reprocessamento
      loadCnpjs();
    } catch (err) {
      setError('Erro ao reprocessar CNPJ: ' + (err.response?.data?.detail || err.message));
    } finally {
      setReprocessing(false);
    }
  };

  // Paginação
  const totalPages = Math.ceil(stats.total / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const displayedCnpjs = cnpjs.slice(startIndex, endIndex);

  // Função para formatar a data
  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }).format(date);
  };

  // Função utilitária para limpar e organizar o HTML do full_result e extrair a URL do brasão
  function cleanFullResultHtml(rawHtml) {
    const parser = new window.DOMParser();
    const doc = parser.parseFromString(rawHtml, 'text/html');
    // Extrair URL do brasão (primeira img do header)
    let brasaoUrl = '';
    const headerImg = doc.querySelector('#interface header img');
    if (headerImg && headerImg.src) {
      brasaoUrl = headerImg.src;
    }
    // Remove <style> e <script>
    doc.querySelectorAll('style, script').forEach(el => el.remove());
    // Pega só o conteúdo do #interface (ou body se não existir)
    let mainContent = doc.querySelector('#interface') || doc.body;
    // Remove imagens do brasão
    mainContent.querySelectorAll('img').forEach(img => {
      if (
        img.src.includes('uploadGgImagem') ||
        img.src.includes('brasao') ||
        img.src.includes('nova_friburgo')
      ) {
        img.remove();
      }
    });
    // Remove atributos de estilo inline e classes
    mainContent.querySelectorAll('[style], [class]').forEach(el => {
      el.removeAttribute('style');
      el.removeAttribute('class');
    });
    // Remove atributos de alinhamento e largura
    mainContent.querySelectorAll('[align], [width], [height]').forEach(el => {
      el.removeAttribute('align');
      el.removeAttribute('width');
      el.removeAttribute('height');
    });
    // Remove divs absolutamente posicionadas
    mainContent.querySelectorAll('div').forEach(div => {
      if (div.getAttribute('style') && div.getAttribute('style').includes('position: absolute')) {
        div.remove();
      }
    });
    // Retorna HTML limpo e URL do brasão
    return {
      html: mainContent.innerHTML,
      brasaoUrl
    };
  }

  const handleShowFullResult = (html, cnpjId) => {
    const { html: cleanedHtml, brasaoUrl } = cleanFullResultHtml(html);
    
    // Create a unique key for this specific certificate
    const storageKey = `certidao_${cnpjId}`;
    
    // Store data in sessionStorage before opening new window
    sessionStorage.setItem(storageKey, JSON.stringify({
      htmlContent: cleanedHtml,
      brasaoUrl: brasaoUrl
    }));
    
    // Open new window without the key parameter
    window.open(`/certidao/${cnpjId}`, '_blank');
  };

  // Modifique o renderStatus para exibir um resumo do texto quando estiver concluído
  const renderStatus = (status, resultado) => {
    switch(status) {
      case 'concluido':
        return (
          <div>
            <span className="status-badge success"><FiCheckCircle /> Concluído</span>
            {resultado && (
              <div className="resultado-resumo">
                {resultado.length > 100 ? resultado.substring(0, 100) + '...' : resultado}
              </div>
            )}
          </div>
        );
      case 'erro':
        return (
          <div>
            <span className="status-badge error"><FiAlertCircle /> Erro</span>
            {resultado && (
              <div className="resultado-erro">
                {resultado.length > 100 ? resultado.substring(0, 100) + '...' : resultado}
              </div>
            )}
          </div>
        );
      case 'processando':
        return <span className="status-badge processing"><FiRefreshCw className="spinning" /> Processando</span>;
      case 'pendente':
        return <span className="status-badge pending">Pendente</span>;
      default:
        return <span className="status-badge">{status}</span>;
    }
  };

  // Renderização das ações para cada linha da tabela
  const renderActions = (cnpj) => {
    if (cnpj.status === 'erro') {
      return (
        <button 
          className="btn btn-sm btn-danger" 
          onClick={() => handleReprocessOne(cnpj.id, cnpj.cnpj)}
          disabled={reprocessing}
        >
          <FiRefreshCw className={reprocessing ? 'spinning' : ''} />
          <span>{reprocessing ? 'Reprocessando...' : 'Reprocessar'}</span>
        </button>
      );
    }
    
    if (cnpj.status === 'concluido') {
      return (
        <button 
          className="btn btn-sm btn-info" 
          onClick={() => handleShowFullResult(cnpj.full_result, cnpj.id)}
        >
          <FiFileText /> Ver Certidão
        </button>
      );
    }
    
    return null;
  };

  // Add this function for the batch processing config
  const toggleBatchOptions = () => {
    setBatchReprocessConfig(prev => ({...prev, showOptions: !prev.showOptions}));
  };

  const handleConfigChange = (e) => {
    const { name, value } = e.target;
    setBatchReprocessConfig(prev => ({...prev, [name]: value}));
  };

  return (
    <div className="consulta-container">
      <h1>Consulta de CNPJs</h1>
      
      <div className="stats-container">
        <div className="stat-box">
          <span className="stat-label">Total</span>
          <span className="stat-value">{stats.total}</span>
        </div>
        <div className="stat-box pending">
          <span className="stat-label">Pendentes</span>
          <span className="stat-value">{stats.pendentes}</span>
        </div>
        <div className="stat-box processing">
          <span className="stat-label">Processando</span>
          <span className="stat-value">{stats.processando}</span>
        </div>
        <div className="stat-box success">
          <span className="stat-label">Concluídos</span>
          <span className="stat-value">{stats.concluidos}</span>
        </div>
        <div className="stat-box error">
          <span className="stat-label">Erros</span>
          <span className="stat-value">{stats.erros}</span>
        </div>
      </div>
      
      <div className="filter-container">
        <div className="filter-header">
          <h2><FiFilter /> Filtros</h2>
          <div className="auto-refresh">
            <label htmlFor="autoRefresh">
              <input 
                type="checkbox" 
                id="autoRefresh" 
                checked={autoRefresh} 
                onChange={toggleAutoRefresh} 
              />
              Atualização automática ({autoRefresh ? "Ativada" : "Desativada"})
            </label>
          </div>
        </div>
        <form onSubmit={applyFilters}>
          <div className="filter-row">
            <div className="filter-group">
              <label htmlFor="status">Status</label>
              <select 
                id="status" 
                name="status" 
                value={filters.status} 
                onChange={handleFilterChange}
              >
                <option value="">Todos</option>
                <option value="pendente">Pendente</option>
                <option value="processando">Processando</option>
                <option value="concluido">Concluído</option>
                <option value="erro">Erro</option>
              </select>
            </div>
            
            <div className="filter-group full-width">
              <label htmlFor="textoErro">Texto do Erro</label>
              <input 
                type="text" 
                id="textoErro" 
                name="textoErro" 
                placeholder="Ex: PDF não encontrado" 
                value={filters.textoErro} 
                onChange={handleFilterChange}
              />
            </div>
          </div>
          
          <div className="filter-actions">
            <button type="submit" className="btn btn-primary">
              <FiSearch /> Aplicar Filtros
            </button>
            <button type="button" className="btn btn-secondary" onClick={clearFilters}>
              <FiX /> Limpar Filtros
            </button>
            {stats.erros > 0 && (
              <div className="action-dropdown batch-reprocess">
                <button 
                  type="button" 
                  className="btn btn-danger" 
                  onClick={toggleBatchOptions}
                  disabled={reprocessing}
                >
                  <FiRefreshCw className={reprocessing ? 'spinning' : ''} />
                  <span>{reprocessing ? 'Reprocessando...' : 'Reprocessar Todos os Erros'}</span>
                  <FiChevronDown size={14} style={{ marginLeft: '4px' }} />
                </button>

                {batchReprocessConfig.showOptions && (
                  <div className="dropdown-menu batch-options">
                    <h4 className="dropdown-header">Configurações</h4>
                    <div className="dropdown-config">
                      <div className="config-group">
                        <label htmlFor="limite">Limite de CNPJs a processar:</label>
                        <input
                          type="number"
                          id="limite"
                          name="limite"
                          min="1"
                          max="1000"
                          value={batchReprocessConfig.limite}
                          onChange={handleConfigChange}
                        />
                      </div>
                    </div>
                    <div className="dropdown-actions">
                      <button 
                        className="dropdown-item"
                        onClick={() => handleReprocessAll(batchReprocessConfig)}
                      >
                        Reprocessar com este limite
                      </button>
                      <button 
                        className="dropdown-item"
                        onClick={() => handleReprocessAll({limite: 100})}
                      >
                        Reprocessar com limite padrão (100)
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </form>
      </div>
      
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
      
      <div className="cnpj-list">
        <h2>Lista de CNPJs</h2>
        
        {loading ? (
          <div className="loading">Carregando dados...</div>
        ) : cnpjs.length === 0 ? (
          <div className="empty-state">Nenhum CNPJ encontrado para os filtros selecionados.</div>
        ) : (
          <>
            <table className="cnpj-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Nome</th>
                  <th>CNPJ</th>
                  <th>Status</th>
                  <th>Data Criação</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {displayedCnpjs.map(cnpj => (
                  <tr key={cnpj.id} className={`row-${cnpj.status}`}>
                    <td>{cnpj.id}</td>
                    <td>{cnpj.nome}</td>
                    <td>{cnpj.cnpj}</td>
                    <td>{renderStatus(cnpj.status, cnpj.resultado)}</td>
                    <td>{formatDate(cnpj.data_criacao)}</td>
                    <td>
                      {renderActions(cnpj)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            
            {/* Paginação */}
            {totalPages > 1 && (
              <div className="pagination">
                <button 
                  onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                  disabled={currentPage === 1}
                  className="pagination-btn"
                >
                  Anterior
                </button>
                
                <span className="page-info">
                  Página {currentPage} de {totalPages}
                </span>
                
                <button 
                  onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                  disabled={currentPage === totalPages}
                  className="pagination-btn"
                >
                  Próxima
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default ConsultaPage; 