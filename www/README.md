# /www

In this directory, we have web tech tooling, notably:

* A frontend starter for web-based UI to control a TouchDesigner app (and vice versa), via the Oversite module, which uses WebSockets to create a shared state system between the browser and TD. 

# Install

```bash
cd www
npm install
```

# Run

Start both the Vite frontend server and the Oversite WebSocket & tools server:

```bash
npm run all
```