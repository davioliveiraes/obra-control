FROM node:24.21.0-bookworm-slim

WORKDIR /app
RUN chown node:node /app
USER node

COPY --chown=node:node package.json package-lock.json .npmrc ./
RUN node --version && npm --version && npm ci

COPY --chown=node:node index.html vite.config.ts tsconfig*.json eslint.config.js ./
COPY --chown=node:node .prettierrc.json .prettierignore README.md ./
COPY --chown=node:node src ./src

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
