import React from 'react';
import './CustomCheckbox.css';

const CustomCheckbox = ({ 
  id, 
  checked, 
  onChange, 
  disabled = false,
  indeterminate = false,
  ariaLabel
}) => {
  const checkboxRef = React.useRef(null);
  
  React.useEffect(() => {
    if (checkboxRef.current) {
      checkboxRef.current.indeterminate = indeterminate;
    }
  }, [indeterminate]);

  return (
    <label className="custom-checkbox-container" aria-label={ariaLabel}>
      <input
        ref={checkboxRef}
        type="checkbox"
        id={id}
        checked={checked}
        onChange={onChange}
        disabled={disabled}
      />
      <span className="checkmark"></span>
    </label>
  );
};

export default CustomCheckbox; 