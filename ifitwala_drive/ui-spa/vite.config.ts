import path from 'node:path'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig({
	plugins: [vue()],
	resolve: {
		alias: {
			'@': path.resolve(__dirname, 'src')
		}
	},
	base: '/assets/ifitwala_drive/vite/',
	build: {
		outDir: path.resolve(__dirname, '../public/vite'),
		emptyOutDir: true,
		manifest: true,
		sourcemap: false,
		rollupOptions: {
			input: {
				'src/apps/workspace/main.ts': path.resolve(__dirname, 'src/apps/workspace/main.ts')
			},
			output: {
				entryFileNames: 'assets/[name].[hash].js',
				chunkFileNames: 'assets/[name].[hash].js',
				assetFileNames: 'assets/[name].[hash][extname]'
			}
		}
	}
})
