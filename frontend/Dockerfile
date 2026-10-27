FROM node:20-alpine as builder

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Telegram Mini App — отдельная сборка (свой конфиг, свой outDir, base=/miniapp/).
# Отдельной командой намеренно: сборка сайта выше не меняется, и если мини-апп
# не соберётся, из лога сразу видно, что упало именно оно.
RUN npm run build:miniapp

# Production stage
FROM nginx:alpine

# Copy built files
COPY --from=builder /app/dist /usr/share/nginx/html
# Мини-апп ложится в подкаталог: сайт и он живут на одном домене, поэтому
# запросы к /api проксируются тем же блоком и никакого CORS не возникает.
COPY --from=builder /app/dist-miniapp /usr/share/nginx/html/miniapp

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
