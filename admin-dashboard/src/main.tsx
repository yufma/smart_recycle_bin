import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles.css';
import './design.css';

async function start() {
  if (import.meta.env.MODE === 'pages') {
    const { installPublicDemo } = await import('./publicDemo');
    installPublicDemo();
  }
  ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
}
void start();
