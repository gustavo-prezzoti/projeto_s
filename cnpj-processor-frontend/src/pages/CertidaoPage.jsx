import React, { useEffect, useState } from 'react';
import { useParams, useLocation } from 'react-router-dom';
import { FiPrinter, FiArrowLeft } from 'react-icons/fi';
import './CertidaoPage.css';

const CertidaoPage = () => {
  const { id } = useParams();
  const location = useLocation();
  const [loading, setLoading] = useState(true);
  const [brasaoUrl, setBrasaoUrl] = useState('');
  const [title, setTitle] = useState('');
  const [certNumber, setCertNumber] = useState('');
  const [headerContent, setHeaderContent] = useState('');
  const [mainContent, setMainContent] = useState('');

  // Get data from sessionStorage using the ID
  useEffect(() => {
    // Try to get data using the ID as the storage key
    const storageKey = `certidao_${id}`;
    const storedData = sessionStorage.getItem(storageKey);
    
    if (storedData) {
      try {
        const { htmlContent, brasaoUrl } = JSON.parse(storedData);
        processHtmlContent(htmlContent, brasaoUrl);
        setLoading(false);
        return;
      } catch (error) {
        console.error('Error parsing stored data:', error);
      }
    }

    // Fallback to location state if available
    if (location.state) {
      const { htmlContent, brasaoUrl } = location.state;
      
      if (htmlContent) {
        processHtmlContent(htmlContent, brasaoUrl);
        setLoading(false);
        return;
      }
    }
    
    // If no data is found, show error state
    setLoading(false);
    setTitle('Dados da certidão não encontrados');
  }, [location, id]);

  // Função para processar o HTML e extrair partes específicas
  const processHtmlContent = (rawHtml, brasaoUrl) => {
    // Salvar o brasão
    setBrasaoUrl(brasaoUrl || '');
    
    // Processar o HTML
    try {
      const parser = new window.DOMParser();
      const doc = parser.parseFromString(`<div>${rawHtml}</div>`, 'text/html');
      
      // Extrair header
      const header = doc.querySelector('header');
      let headerHtml = '';
      let titleHtml = '';
      
      if (header) {
        // Extrair h3 (título) de dentro do header, se existir
        const h3 = header.querySelector('h3');
        if (h3) {
          titleHtml = h3.outerHTML;
          h3.remove();
        }
        headerHtml = header.innerHTML;
        header.remove();
      }
      
      // Se não achou título no header, procurar fora
      if (!titleHtml) {
        const h3 = doc.querySelector('h3');
        if (h3) {
          titleHtml = h3.outerHTML;
          h3.remove();
        }
      }
      
      // Processar o título e extrair o número da certidão
      if (titleHtml) {
        const titleDoc = parser.parseFromString(titleHtml, 'text/html');
        let raw = titleDoc.body.innerHTML.replace(/<br\/?\s*>/gi, '\n');
        const lines = raw.split(/\n|<br\/?\s*>/i).map(l => l.trim()).filter(Boolean);
        
        const titleLine = lines.find(l => l.toUpperCase().includes('CERTIDÃO'));
        const numLine = lines.find(l => l.toUpperCase().includes('Nº') || l.toUpperCase().includes('N°'));
        
        setTitle(titleLine || '');
        setCertNumber(numLine || '');
      }
      
      // Processamento adicional do conteúdo principal
      let mainHtml = doc.body.innerHTML;
      
      // Alinhar "Emitido em:" à direita
      try {
        mainHtml = mainHtml.replace(/(<p[^>]*>\s*Emitido em:[^<]*<\/p>)/gi, (match) => {
          if (/class=["'][^"']*["']/.test(match)) {
            return match.replace(/class=["']([^"']*)["']/, 'class="$1 emitido-direita"');
          } else {
            return match.replace('<p', '<p class="emitido-direita"');
          }
        });
      } catch (error) {
        console.error('Erro ao processar alinhamento:', error);
      }
      
      // Atualizar os estados
      setHeaderContent(headerHtml);
      setMainContent(mainHtml);
    } catch (error) {
      console.error('Erro ao processar HTML:', error);
      setMainContent(rawHtml);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  const handleBack = () => {
    window.history.back();
  };

  if (loading) {
    return <div className="certidao-loading">Carregando documento...</div>;
  }

  return (
    <div className="certidao-page">
      <div className="certidao-actions">
        <button onClick={handleBack} className="back-button">
          <FiArrowLeft size={20} /> Voltar
        </button>
        <button onClick={handlePrint} className="print-button">
          <FiPrinter size={20} /> Imprimir
        </button>
      </div>
      
      <div className="certidao-container">
        {/* Watermark as real DOM element for better print support */}
        <div className="certidao-watermark">
          {brasaoUrl ? (
            <img src={brasaoUrl} alt="" />
          ) : (
            <div className="default-watermark">NF</div>
          )}
        </div>
        
        {/* Header com brasão ao lado do texto */}
        {headerContent && (
          <div className="certidao-header">
            {brasaoUrl && (
              <div className="certidao-brasao">
                <img src={brasaoUrl} alt="Brasão Prefeitura" />
              </div>
            )}
            <div className="certidao-header-text" dangerouslySetInnerHTML={{ __html: headerContent }} />
          </div>
        )}
        
        {/* Título centralizado e destacado */}
        {(title || certNumber) && (
          <div className="certidao-title">
            {title && <h3>{title}</h3>}
            {certNumber && <div className="certidao-numero">{certNumber}</div>}
          </div>
        )}
        
        {/* Conteúdo principal */}
        {mainContent ? (
          <div className="certidao-content" dangerouslySetInnerHTML={{ __html: mainContent }} />
        ) : (
          <div className="certidao-error">
            <p>Não foi possível carregar o conteúdo da certidão.</p>
            <p>Por favor, retorne e tente novamente.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default CertidaoPage; 