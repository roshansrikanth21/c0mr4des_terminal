FROM node:20-slim

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy frontend code
COPY . .

# Expose Vite port
EXPOSE 3000

# Run development server with host binding
CMD ["npm", "run", "dev", "--", "--host"]
