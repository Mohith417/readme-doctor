# React

[![GitHub license](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/facebook/react/blob/main/LICENSE)
[![npm version](https://img.shields.io/npm/v/react.svg?style=flat)](https://www.npmjs.com/package/react)
[![(Runtime) Build and Test](https://github.com/facebook/react/actions/workflows/runtime_build_and_test.yml/badge.svg)](https://github.com/facebook/react/actions/workflows/runtime_build_and_test.yml)
[![(Compiler) TypeScript](https://github.com/facebook/react/actions/workflows/compiler_typescript.yml/badge.svg?branch=main)](https://github.com/facebook/react/actions/workflows/compiler_typescript.yml)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://legacy.reactjs.org/docs/how-to-contribute.html#your-first-pull-request)

> **React** – The library for web and native user interfaces.

---

## 📖 What Is React?

React is a declarative, component-based JavaScript library for building fast, flexible, and scalable user interfaces across web, mobile, and server environments. It lets you describe the UI in a declarative way and manages the DOM for you, making it easier to create interactive applications that are maintainable and testable.

### Why React?

- **Declarative UI** – Write what you want to see on the screen; React updates the DOM efficiently when data changes.
- **Component‑oriented** – Reusable, encapsulated pieces of UI that can be composed into complex interfaces.
- **Unopinionated** – Works with any backend, bundler, or additional libraries. It can render on the web, on Node.js (SSR), and on mobile via React Native.

React is used by millions of developers and companies worldwide, powering applications like Facebook, Instagram, Netflix, Airbnb, and many more.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Virtual DOM** | Diffing algorithm that updates only what has changed for optimal performance. |
| **JSX Syntax** | Write HTML‑like syntax directly in JavaScript for clearer component definitions. |
| **Hooks** | `useState`, `useEffect`, `useContext`, and custom hooks for clean, functional component logic. |
| **Context API** | Global state without prop‑drilling, ideal for theme, auth, or locale data. |
| **Concurrent Mode** | Graceful rendering of large UI trees without blocking user interactions. |
| **Server‑Side Rendering** | Hydration support for fast initial page loads and SEO. |
| **TypeScript Support** | First‑class typing and excellent type inference. |
| **React Native Compatibility** | The same concepts for building cross‑platform mobile apps. |
| **Tooling & Ecosystem** | Rich devtools, community libraries, and official starter kits (Create React App, Next.js, Remix, etc.). |

---

## 📋 Prerequisites

- **Node.js** – 14.x or newer (recommended 18.x+)
- **npm** or **Yarn** – package manager
- (Optional) **TypeScript** – if you prefer typed components

---

## ⚙️ Installation

```bash
# npm
npm install react react-dom

# yarn
yarn add react react-dom
```

> **Tip**: If you’re starting a new project, consider using a starter kit such as Create React App or Vite.  
> 👉 [Create React App](https://create-react-app.dev/) – React + Webpack, Babel, ESLint, etc.  
> 👉 [Vite](https://vitejs.dev/guide/#create-your-first-project) – Lightning‑fast dev server and build tool.

---

## 🚀 Usage

### Basic Component

```tsx
// App.jsx
import React from 'react';

function App() {
  return (
    <div>
      <h1>Hello, React!</h1>
      <Counter />
    </div>
  );
}

export default App;
```

### Functional Component with Hooks

```tsx
// Counter.jsx
import React, { useState } from 'react';

function Counter() {
  const [count, setCount] = useState(0);

  return (
    <div>
      <p>Count: {count}</p>
      <button onClick={() => setCount(c => c + 1)}>Increment</button>
    </div>
  );
}

export default Counter;
```

### Rendering to the DOM

```tsx
// index.jsx
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
```

> **Browser Polyfill** – For older browsers you might need the `react-dom` polyfills or a bundler that includes the appropriate polyfills.

### Server‑Side Rendering (Node.js)

```js
// server.js
const express = require('express');
const { renderToString } = require('react-dom/server');
const App = require('./App').default;

const app = express();

app.get('/', (req, res) => {
  const body = renderToString(<App />);
  res.send(`
    <!DOCTYPE html>
    <html>
      <head><title>React SSR</title></head>
      <body>
        <div id="root">${body}</div>
        <script src="/bundle.js"></script>
      </body>
    </html>
  `);
});

app.listen(3000);
```

### Using React Native

```tsx
// App.tsx (React Native)
import React from 'react';
import { SafeAreaView, Text, Button } from 'react-native';

export default function App() {
  return (
    <SafeAreaView>
      <Text>Welcome to React Native!</Text>
      <Button title="Press me" onPress={() => console.log('Pressed!')} />
    </SafeAreaView>
  );
}
```

---

## 🤝 Contributing

We love contributions! Please read our [Contributing Guide](https://github.com/facebook/react/blob/main/CONTRIBUTING.md) for details on our code of conduct, pull request process, and development workflow.

**Steps to get started**

1. Fork the repository.  
2. Create a feature branch (`git checkout -b feature/your-feature`).  
3. Make your changes with clear commit messages.  
4. Run the tests (`npm test`) and linting (`npm run lint`).  
5. Submit a pull request.

> All contributors must sign our [Contributor License Agreement](https://github.com/facebook/react/blob/main/CLA.md).

---

## 📄 License

React is licensed under the [MIT License](https://github.com/facebook/react/blob/main/LICENSE).

---