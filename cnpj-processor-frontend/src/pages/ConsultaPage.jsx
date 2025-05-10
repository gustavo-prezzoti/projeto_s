import React, { useState, useEffect, useRef } from 'react';
import { consultarCnpjs, reprocessarErros, reprocessarCnpjIndividual, deletarCnpj, deletarCnpjsEmLote } from '../services/api';
import api from '../services/api';
import { FiRefreshCw, FiFilter, FiX, FiSearch, FiAlertCircle, FiCheckCircle, FiFileText, FiChevronDown, FiTrash2 } from 'react-icons/fi';
import './ConsultaPage.css';
import ConfirmationModal from '../components/ConfirmationModal';
import CustomCheckbox from '../components/CustomCheckbox';

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
  const [filterLoading, setFilterLoading] = useState(false);
  const [reprocessing, setReprocessing] = useState(false);
  const [reprocessingIds, setReprocessingIds] = useState([]);
  const [viewingCertificateIds, setViewingCertificateIds] = useState([]);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [filters, setFilters] = useState({
    status: '',
    textoErro: ''
  });
  const [autoRefresh, setAutoRefresh] = useState(true);
  const autoRefreshIntervalRef = useRef(null);
  const tableRef = useRef(null);
  const itemsPerPage = 10;
  const [batchReprocessConfig, setBatchReprocessConfig] = useState({
    showOptions: false,
    limite: 100
  });

  // New state variables for batch deletion
  const [selectedCnpjs, setSelectedCnpjs] = useState([]);
  const [selectAll, setSelectAll] = useState(false);
  const [confirmationModal, setConfirmationModal] = useState({
    isOpen: false,
    title: '',
    message: '',
    items: [],
    isLoading: false
  });
  
  // Store the complete data in a ref to avoid unnecessary re-renders
  const allDataRef = useRef({
    cnpjs: [],
    currentFilters: {}
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
  }, [autoRefresh]); // Remove filters and currentPage from dependencies

  // Update displayed items when page changes
  useEffect(() => {
    updateDisplayedItems();
    // Clear selections when changing pages
    setSelectedCnpjs([]);
    setSelectAll(false);
  }, [currentPage]);

  // Effect to handle "select all" checkbox state
  useEffect(() => {
    if (cnpjs.length === 0) {
      setSelectAll(false);
      return;
    }

    if (selectedCnpjs.length === cnpjs.length) {
      setSelectAll(true);
    } else {
      setSelectAll(false);
    }
  }, [selectedCnpjs, cnpjs]);

  // Function to update displayed items without fetching new data
  const updateDisplayedItems = () => {
    // Calculate pagination
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    
    // Get the slice of data to display
    const displayedItems = allDataRef.current.cnpjs.slice(startIndex, endIndex);
    
    // Update state with only the items to display
    setCnpjs(displayedItems);
  };

  const loadCnpjs = async () => {
    setLoading(true);
    setError(null);
    setMessage(null);

    try {
      const filterParams = {
        ...filters,
      };
      
      // Remover parâmetros vazios
      Object.keys(filterParams).forEach(key => 
        !filterParams[key] && delete filterParams[key]
      );
      
      // Adicionar parâmetro para indicar que a busca deve ser por qualquer posição
      if (filterParams.textoErro) {
        filterParams.matchAnywhere = true;
      }
      
      const response = await consultarCnpjs(filterParams);
      
      // Verificar se a resposta é um array (nova API) ou um objeto com propriedade 'cnpjs' (API antiga)
      const data = Array.isArray(response) ? response : (response.cnpjs || []);
      
      // Filtragem no cliente para garantir match em qualquer posição se o backend não suportar
      let filteredCnpjs = [...data];
      
      // Se houver filtro de texto, filtrar localmente garantindo que o match seja em qualquer posição
      if (filters.textoErro) {
        const searchTerm = filters.textoErro.toLowerCase();
        filteredCnpjs = filteredCnpjs.filter(cnpj => {
          // Para status de erro, verificar se o texto de erro contém o termo buscado
          if (cnpj.status === 'erro' && cnpj.resultado) {
            return cnpj.resultado.toLowerCase().includes(searchTerm);
          }
          
          // Para CNPJs concluídos, verificar se o resultado contém o termo buscado
          if (cnpj.status === 'concluido' && cnpj.resultado) {
            return cnpj.resultado.toLowerCase().includes(searchTerm);
          }
          
          // Verificar também na razão social, município e CNPJ
          return (cnpj.razao_social?.toLowerCase().includes(searchTerm)) || 
                 (cnpj.cnpj?.toLowerCase().includes(searchTerm)) ||
                 (cnpj.municipio?.toLowerCase().includes(searchTerm));
        });
      }
      
      // Store complete data in ref
      allDataRef.current = {
        cnpjs: filteredCnpjs,
        currentFilters: {...filters}
      };
      
      // Reset to first page when filters change
      setCurrentPage(1);
      
      // Update displayed items for the first page
      const startIndex = 0;
      const endIndex = itemsPerPage;
      setCnpjs(allDataRef.current.cnpjs.slice(startIndex, endIndex));
      
      // Calcular estatísticas com base nos dados filtrados
      const stats = {
        total: filteredCnpjs.length,
        pendentes: filteredCnpjs.filter(item => item.status === 'pendente').length,
        processando: filteredCnpjs.filter(item => item.status === 'processando').length,
        concluidos: filteredCnpjs.filter(item => item.status === 'concluido').length,
        erros: filteredCnpjs.filter(item => item.status === 'erro').length
      };
      
      setStats(stats);
      
    } catch (error) {
      // eslint-disable-next-line no-unused-vars
      console.error('Erro ao carregar CNPJs:', error);
      setError('Falha ao processar');
    } finally {
      setLoading(false);
    }
  };

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
      
      // Adicionar parâmetro para indicar que a busca deve ser por qualquer posição
      if (filterParams.textoErro) {
        filterParams.matchAnywhere = true;
      }
      
      const response = await consultarCnpjs(filterParams);
      
      // Verificar se a resposta é um array (nova API) ou um objeto com propriedade 'cnpjs' (API antiga)
      const data = Array.isArray(response) ? response : (response.cnpjs || []);
      
      // Filtragem no cliente para garantir match em qualquer posição se o backend não suportar
      let filteredCnpjs = [...data];
      
      // Se houver filtro de texto, filtrar localmente garantindo que o match seja em qualquer posição
      if (filters.textoErro) {
        const searchTerm = filters.textoErro.toLowerCase();
        filteredCnpjs = filteredCnpjs.filter(cnpj => {
          // Para status de erro, verificar se o texto de erro contém o termo buscado
          if (cnpj.status === 'erro' && cnpj.resultado) {
            return cnpj.resultado.toLowerCase().includes(searchTerm);
          }
          
          // Para CNPJs concluídos, verificar se o resultado contém o termo buscado
          if (cnpj.status === 'concluido' && cnpj.resultado) {
            return cnpj.resultado.toLowerCase().includes(searchTerm);
          }
          
          // Verificar também na razão social, município e CNPJ
          return (cnpj.razao_social?.toLowerCase().includes(searchTerm)) || 
                 (cnpj.cnpj?.toLowerCase().includes(searchTerm)) ||
                 (cnpj.municipio?.toLowerCase().includes(searchTerm));
        });
      }
      
      // Store complete data in ref
      allDataRef.current = {
        cnpjs: filteredCnpjs,
        currentFilters: {...filters}
      };
      
      // Update displayed items based on current page
      updateDisplayedItems();
      
      // Calcular estatísticas com base nos dados filtrados
      const stats = {
        total: filteredCnpjs.length,
        pendentes: filteredCnpjs.filter(item => item.status === 'pendente').length,
        processando: filteredCnpjs.filter(item => item.status === 'processando').length,
        concluidos: filteredCnpjs.filter(item => item.status === 'concluido').length,
        erros: filteredCnpjs.filter(item => item.status === 'erro').length
      };
      
      setStats(stats);
      
    } catch (error) {
      // eslint-disable-next-line no-unused-vars
      console.error('Erro na atualização automática:', error);
      // Não mostrar erro para o usuário em atualizações silenciosas
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
    setFilterLoading(true);
    setCurrentPage(1); // Resetar para a primeira página ao aplicar filtros
    loadCnpjs().finally(() => {
      setFilterLoading(false);
    });
  };

  const clearFilters = () => {
    setFilterLoading(true);
    setFilters({
      status: '',
      textoErro: ''
    });
    
    // Aplicar filtros limpos imediatamente
    loadCnpjs().finally(() => {
      setFilterLoading(false);
    });
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
      setError('Falha ao processar');
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
      
      // Instead of reloading all data, update current list state
      if (result.total_processed > 0) {
        if (filters.status === 'erro') {
          // If we're filtered to just errors, we might need to remove all items
          // or only some based on text error filter
          if (textoErro) {
            // Filter out items that match the error text
            const regex = new RegExp(textoErro, 'i');
            allDataRef.current.cnpjs = allDataRef.current.cnpjs.filter(
              item => !(item.status === 'erro' && item.resultado && regex.test(item.resultado))
            );
          } else {
            // If no specific error text, all error items would be reprocessed
            allDataRef.current.cnpjs = allDataRef.current.cnpjs.filter(
              item => item.status !== 'erro'
            );
          }
        } else {
          // If we're showing all statuses, just remove the error ones that match filter
          if (textoErro) {
            const regex = new RegExp(textoErro, 'i');
            allDataRef.current.cnpjs = allDataRef.current.cnpjs.filter(
              item => !(item.status === 'erro' && item.resultado && regex.test(item.resultado))
            );
          } else {
            // If no text filter, remove all error items
            allDataRef.current.cnpjs = allDataRef.current.cnpjs.filter(
              item => item.status !== 'erro'
            );
          }
        }
        
        // Update stats
        setStats(prev => ({
          ...prev,
          erros: Math.max(0, prev.erros - result.total_processed),
          processando: prev.processando + result.total_processed
        }));
        
        // Update displayed items
        updateDisplayedItems();
      }
          // eslint-disable-next-line no-unused-vars
    } catch (_) {
      setError('Falha ao processar');
    } finally {
      setReprocessing(false);
      // Close options after processing
      setBatchReprocessConfig(prev => ({...prev, showOptions: false}));
    }
  };

  const handleReprocessOne = async (id, cnpj) => {
    // Add ID to loading state
    setReprocessingIds(prev => [...prev, id]);
    setError(null);
    setMessage(null);
    
    try {
      // Use the dedicated API for individual CNPJ reprocessing
      await reprocessarCnpjIndividual(id, false);
      setMessage(`CNPJ ${cnpj} enviado para reprocessamento!`);
      
      // Instead of reloading all data, just remove this CNPJ from the current list
      // Remove from the main data source
      allDataRef.current.cnpjs = allDataRef.current.cnpjs.filter(item => item.id !== id);
      
      // Update stats
      setStats(prev => ({
        ...prev,
        erros: Math.max(0, prev.erros - 1),
        processando: prev.processando + 1
      }));
      
      // Update the displayed items
      updateDisplayedItems();
          // eslint-disable-next-line no-unused-vars
    } catch (_) {
      setError('Falha ao processar');
    } finally {
      // Remove ID from loading state
      setReprocessingIds(prev => prev.filter(item => item !== id));
    }
  };

  // Handle pagination changes without scroll issues
  const handlePageChange = (newPage) => {
    // Just change the page without scrolling
    setCurrentPage(newPage);
  };

  // Calculate total pages based on the total items, not just the displayed ones
  const totalPages = Math.ceil(allDataRef.current.cnpjs.length / itemsPerPage);

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
    // Add ID to loading state
    setViewingCertificateIds(prev => [...prev, cnpjId]);
    
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
    
    // Remove ID from loading state after a short delay
    setTimeout(() => {
      setViewingCertificateIds(prev => prev.filter(id => id !== cnpjId));
    }, 500);
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
            <div className="resultado-erro">Falha ao processar</div>
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

  const handleDeleteCnpj = (id, cnpj) => {
    handleOpenDeleteModal(id, cnpj);
  };

  // Renderização das ações para cada linha da tabela
  const renderActions = (cnpj) => {
    const isReprocessing = reprocessingIds.includes(cnpj.id);
    const isViewingCertificate = viewingCertificateIds.includes(cnpj.id);
    
    return (
      <div className="action-buttons">
        {/* Botão de exclusão (sempre visível) */}
        <button 
          className="btn btn-sm btn-delete" 
          onClick={() => handleDeleteCnpj(cnpj.id, cnpj.cnpj)}
          title="Excluir CNPJ"
        >
          <FiTrash2 />
        </button>
        
        {/* Botão de PDF se disponível */}
        {cnpj.pdf_path && (
          <a 
            href={`/api${cnpj.pdf_path}`}
            className="btn btn-sm btn-success" 
            target="_blank"
            rel="noopener noreferrer"
            title="Ver PDF"
          >
            <FiFileText />
          </a>
        )}
        
        {/* Botão de reprocessamento se estiver com erro */}
        {cnpj.status === 'erro' && (
          <button 
            className="btn btn-sm btn-danger" 
            onClick={() => handleReprocessOne(cnpj.id, cnpj.cnpj)}
            disabled={isReprocessing}
            title="Reprocessar CNPJ"
          >
            <FiRefreshCw className={isReprocessing ? 'spinning' : ''} />
          </button>
        )}
        
        {/* Botão para ver certidão se estiver concluído */}
        {cnpj.status === 'concluido' && (
          <button 
            className="btn btn-sm btn-info" 
            onClick={() => handleShowFullResult(cnpj.full_result, cnpj.id)}
            disabled={isViewingCertificate}
            title="Ver Certidão"
          >
            <FiFileText />
          </button>
        )}
      </div>
    );
  };

  // Add this function for the batch processing config
  const toggleBatchOptions = () => {
    setBatchReprocessConfig(prev => ({...prev, showOptions: !prev.showOptions}));
  };

  const handleConfigChange = (e) => {
    const { name, value } = e.target;
    setBatchReprocessConfig(prev => ({...prev, [name]: value}));
  };

  const handleToggleSelect = (id) => {
    setSelectedCnpjs(prevSelected => {
      if (prevSelected.includes(id)) {
        return prevSelected.filter(item => item !== id);
      } else {
        return [...prevSelected, id];
      }
    });
  };

  const handleToggleSelectAll = () => {
    if (selectAll) {
      // If all are selected, deselect all
      setSelectedCnpjs([]);
    } else {
      // Otherwise, select all currently displayed items
      setSelectedCnpjs(cnpjs.map(item => item.id));
    }
  };

  const handleOpenDeleteModal = (id = null, cnpj = null) => {
    // If id is provided, it's a single item deletion
    if (id !== null) {
      setConfirmationModal({
        isOpen: true,
        title: 'Confirmar Exclusão',
        message: `Tem certeza que deseja excluir o CNPJ ${cnpj}?`,
        items: [{ id, cnpj }],
        isLoading: false
      });
    } 
    // Otherwise it's a batch deletion
    else if (selectedCnpjs.length > 0) {
      const selectedItems = cnpjs.filter(item => selectedCnpjs.includes(item.id));
      setConfirmationModal({
        isOpen: true,
        title: 'Confirmar Exclusão em Lote',
        message: `Tem certeza que deseja excluir ${selectedCnpjs.length} CNPJ(s) selecionados?`,
        items: selectedItems,
        isLoading: false
      });
    }
  };

  const handleCloseDeleteModal = () => {
    setConfirmationModal(prev => ({
      ...prev,
      isOpen: false,
      isLoading: false
    }));
  };

  const handleDeleteConfirm = async () => {
    const { items } = confirmationModal;
    
    // Set loading state in the modal
    setConfirmationModal(prev => ({...prev, isLoading: true}));
    
    try {
      let success = false;
      let responseMessage = null;
      
      // If only one item, use single delete API
      if (items.length === 1) {
        const id = items[0].id;
        success = await deletarCnpj(id);
        if (success) {
          responseMessage = `CNPJ ${items[0].cnpj} excluído com sucesso!`;
        }
      } 
      // Otherwise use batch delete API
      else if (items.length > 1) {
        const ids = items.map(item => item.id);
        try {
          // Get response directly from API
          const response = await deletarCnpjsEmLote(ids);
          
          // Check if successful (204 No Content or 200 OK with success message)
          if (response.status === 204 || 
              (response.data && response.data.status === "success")) {
            success = true;
            
            // Get message from response if available
            if (response.data && response.data.message) {
              responseMessage = response.data.message;
            }
          }
        } catch (error) {
          console.error('Erro ao excluir CNPJs em lote:', error);
          success = false;
        }
      }
      
      if (success) {
        // Update data after successful deletion
        
        // Remove deleted items from the complete data list
        const deletedIds = items.map(item => item.id);
        allDataRef.current.cnpjs = allDataRef.current.cnpjs.filter(
          item => !deletedIds.includes(item.id)
        );
        
        // Update stats
        if (allDataRef.current.cnpjs.length > 0) {
          const newStats = {
            total: allDataRef.current.cnpjs.length,
            pendentes: allDataRef.current.cnpjs.filter(item => item.status === 'pendente').length,
            processando: allDataRef.current.cnpjs.filter(item => item.status === 'processando').length,
            concluidos: allDataRef.current.cnpjs.filter(item => item.status === 'concluido').length,
            erros: allDataRef.current.cnpjs.filter(item => item.status === 'erro').length
          };
          setStats(newStats);
        } else {
          setStats({
            total: 0,
            pendentes: 0,
            processando: 0,
            concluidos: 0,
            erros: 0
          });
        }
        
        // Set success message - use API response message if available
        setMessage(
          responseMessage || 
          (items.length === 1 
            ? `CNPJ ${items[0].cnpj} excluído com sucesso!` 
            : `${items.length} CNPJs excluídos com sucesso!`)
        );
        
        // Clear selection
        setSelectedCnpjs([]);
        
        // Update displayed items
        updateDisplayedItems();
      } else {
        setError('Falha ao processar');
      }
    } catch (error) {
      // eslint-disable-next-line no-unused-vars
      console.error('Erro ao excluir CNPJs:', error);
      setError('Falha ao processar');
    } finally {
      // Close modal and reset state
      handleCloseDeleteModal();
    }
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
              <label htmlFor="textoErro">Filtro de pesquisa (busca em qualquer posição)</label>
              <input 
                type="text" 
                id="textoErro" 
                name="textoErro" 
                placeholder="Busca em qualquer posição no texto, CNPJ, razão social ou município" 
                value={filters.textoErro} 
                onChange={handleFilterChange}
              />
            </div>
          </div>
          
          <div className="filter-actions">
            <button type="submit" className="btn btn-apply-filter" disabled={filterLoading}>
              {filterLoading ? (
                <>
                  <FiRefreshCw className="spinning" /> Aplicando...
                </>
              ) : (
                <>
                  <FiFilter /> Aplicar Filtros
                </>
              )}
            </button>
            <button 
              type="button" 
              className="btn btn-secondary" 
              onClick={clearFilters} 
              disabled={filterLoading}
            >
              {filterLoading ? (
                <>
                  <FiRefreshCw className="spinning" /> Limpando...
                </>
              ) : (
                <>
                  <FiX /> Limpar Filtros
                </>
              )}
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
        <div className="list-header">
          <h2>Lista de CNPJs</h2>
          
          {/* Add batch action controls */}
          {selectedCnpjs.length > 0 && (
            <div className="batch-controls">
              <span className="selected-count">
                {selectedCnpjs.length} {selectedCnpjs.length === 1 ? 'CNPJ selecionado' : 'CNPJs selecionados'}
              </span>
              <button 
                className="btn btn-danger batch-delete-btn"
                onClick={() => handleOpenDeleteModal()}
              >
                <FiTrash2 /> Excluir Selecionados
              </button>
            </div>
          )}
        </div>
        
        {loading ? (
          <div className="loading">Carregando dados...</div>
        ) : cnpjs.length === 0 ? (
          <div className="empty-state">
            {filters.textoErro ? (
              <>
                <FiSearch style={{ marginRight: '8px' }} />
                Nenhum resultado encontrado que contenha "<strong>{filters.textoErro}</strong>". 
                <br />
                <small>A busca procura o texto em qualquer posição do resultado, CNPJ, razão social ou município.</small>
              </>
            ) : (
              "Nenhum CNPJ encontrado para os filtros selecionados."
            )}
          </div>
        ) : (
          <>
            <table className="cnpj-table" ref={tableRef}>
              <thead>
                <tr>
                  <th className="checkbox-column">
                    <CustomCheckbox
                      id="select-all"
                      checked={selectAll}
                      onChange={handleToggleSelectAll}
                      ariaLabel="Selecionar todos os CNPJs"
                    />
                  </th>
                  <th>ID</th>
                  <th>Razão Social</th>
                  <th>CNPJ</th>
                  <th>Município</th>
                  <th>Status</th>
                  <th>Ações</th>
                </tr>
              </thead>
              <tbody>
                {cnpjs.map(cnpj => (
                  <tr 
                    key={cnpj.id} 
                    className={`row-${cnpj.status} ${selectedCnpjs.includes(cnpj.id) ? 'row-selected' : ''}`}
                  >
                    <td className="checkbox-column">
                      <CustomCheckbox
                        id={`select-${cnpj.id}`}
                        checked={selectedCnpjs.includes(cnpj.id)}
                        onChange={() => handleToggleSelect(cnpj.id)}
                        ariaLabel={`Selecionar CNPJ ${cnpj.cnpj}`}
                      />
                    </td>
                    <td>{cnpj.id}</td>
                    <td>{cnpj.razao_social}</td>
                    <td>{cnpj.cnpj}</td>
                    <td>{cnpj.municipio}</td>
                    <td>{renderStatus(cnpj.status, cnpj.resultado)}</td>
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
                  onClick={() => handlePageChange(Math.max(currentPage - 1, 1))}
                  disabled={currentPage === 1}
                  className="pagination-btn"
                >
                  Anterior
                </button>
                
                <span className="page-info">
                  Página {currentPage} de {totalPages}
                </span>
                
                <button 
                  onClick={() => handlePageChange(Math.min(currentPage + 1, totalPages))}
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
      
      {/* Add Confirmation Modal */}
      <ConfirmationModal
        isOpen={confirmationModal.isOpen}
        title={confirmationModal.title}
        message={confirmationModal.message}
        confirmText="Excluir"
        cancelText="Cancelar"
        onConfirm={handleDeleteConfirm}
        onCancel={handleCloseDeleteModal}
        isLoading={confirmationModal.isLoading}
      />
    </div>
  );
};

export default ConsultaPage; 