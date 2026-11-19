import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './style.css';
import './components/TaskStatus.css';
document.addEventListener('contextmenu', event => event.preventDefault());
document.addEventListener('keydown', event => {
  if (event.ctrlKey && event.shiftKey && !event.altKey && event.key.toLowerCase() === 'r') {
    event.preventDefault(); event.stopImmediatePropagation();
    if (!event.repeat) window.location.reload();
  }
}, true);
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
