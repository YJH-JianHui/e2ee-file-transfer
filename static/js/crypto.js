/**
 * E2EE File Transfer - 前端加密工具库
 * 使用 Web Crypto API 实现 RSA-OAEP 4096 + AES-GCM 256
 */

// ==================== RSA 密钥对生成 ====================

/**
 * 生成 RSA-4096 密钥对
 * @returns {Promise<{publicKey: CryptoKey, privateKey: CryptoKey}>}
 */
async function generateKeyPair() {
    try {
        const keyPair = await window.crypto.subtle.generateKey(
            {
                name: "RSA-OAEP",
                modulusLength: 4096,
                publicExponent: new Uint8Array([1, 0, 1]), // 65537
                hash: "SHA-256"
            },
            true, // 可导出
            ["encrypt", "decrypt"]
        );

        console.log("✅ RSA-4096 密钥对生成成功");
        return keyPair;
    } catch (error) {
        console.error("❌ 密钥对生成失败:", error);
        throw new Error("密钥生成失败，请刷新页面重试");
    }
}

// ==================== 密钥导出（PEM 格式）====================

/**
 * 导出公钥为 PEM 格式
 * @param {CryptoKey} publicKey
 * @returns {Promise<string>}
 */
async function exportPublicKey(publicKey) {
    const exported = await window.crypto.subtle.exportKey("spki", publicKey);
    const exportedAsBase64 = arrayBufferToBase64(exported);
    return `-----BEGIN PUBLIC KEY-----\n${exportedAsBase64}\n-----END PUBLIC KEY-----`;
}

/**
 * 导出私钥为 PEM 格式
 * @param {CryptoKey} privateKey
 * @returns {Promise<string>}
 */
async function exportPrivateKey(privateKey) {
    const exported = await window.crypto.subtle.exportKey("pkcs8", privateKey);
    const exportedAsBase64 = arrayBufferToBase64(exported);
    return `-----BEGIN PRIVATE KEY-----\n${exportedAsBase64}\n-----END PRIVATE KEY-----`;
}

/**
 * 从 PEM 导入公钥
 * @param {string} pem
 * @returns {Promise<CryptoKey>}
 */
async function importPublicKey(pem) {
    const pemContents = pem
        .replace("-----BEGIN PUBLIC KEY-----", "")
        .replace("-----END PUBLIC KEY-----", "")
        .replace(/\s/g, "");

    const binaryDer = base64ToArrayBuffer(pemContents);

    return await window.crypto.subtle.importKey(
        "spki",
        binaryDer,
        {
            name: "RSA-OAEP",
            hash: "SHA-256"
        },
        true,
        ["encrypt"]
    );
}

/**
 * 从 PEM 导入私钥
 * @param {string} pem
 * @returns {Promise<CryptoKey>}
 */
async function importPrivateKey(pem) {
    const pemContents = pem
        .replace("-----BEGIN PRIVATE KEY-----", "")
        .replace("-----END PRIVATE KEY-----", "")
        .replace(/\s/g, "");

    const binaryDer = base64ToArrayBuffer(pemContents);

    return await window.crypto.subtle.importKey(
        "pkcs8",
        binaryDer,
        {
            name: "RSA-OAEP",
            hash: "SHA-256"
        },
        true,
        ["decrypt"]
    );
}

// ==================== AES 对称加密 ====================

/**
 * 生成随机 AES-256 密钥
 * @returns {Promise<CryptoKey>}
 */
async function generateAESKey() {
    return await window.crypto.subtle.generateKey(
        {
            name: "AES-GCM",
            length: 256
        },
        true,
        ["encrypt", "decrypt"]
    );
}

/**
 * 使用 AES-GCM 加密文件
 * @param {ArrayBuffer} fileData
 * @param {CryptoKey} aesKey
 * @returns {Promise<{encrypted: ArrayBuffer, iv: Uint8Array}>}
 */
async function encryptFileWithAES(fileData, aesKey) {
    const iv = window.crypto.getRandomValues(new Uint8Array(12)); // 96-bit IV

    const encrypted = await window.crypto.subtle.encrypt(
        {
            name: "AES-GCM",
            iv: iv
        },
        aesKey,
        fileData
    );

    return { encrypted, iv };
}

/**
 * 使用 AES-GCM 解密文件
 * @param {ArrayBuffer} encryptedData
 * @param {CryptoKey} aesKey
 * @param {Uint8Array} iv
 * @returns {Promise<ArrayBuffer>}
 */
async function decryptFileWithAES(encryptedData, aesKey, iv) {
    return await window.crypto.subtle.decrypt(
        {
            name: "AES-GCM",
            iv: iv
        },
        aesKey,
        encryptedData
    );
}

// ==================== 新增：分块加密/解密 ====================

/**
 * 分块加密大文件
 * @param {File} file
 * @param {CryptoKey} aesKey
 * @param {Function} onProgress 进度回调 (percent)
 * @returns {Promise<{encryptedChunks: Array, iv: Uint8Array}>}
 */
async function encryptFileInChunks(file, aesKey, onProgress) {
    const CHUNK_SIZE = 5 * 1024 * 1024; // 5MB
    const iv = window.crypto.getRandomValues(new Uint8Array(12));
    const encryptedChunks = [];
    const totalChunks = Math.ceil(file.size / CHUNK_SIZE);

    for (let i = 0; i < totalChunks; i++) {
        const start = i * CHUNK_SIZE;
        const end = Math.min(start + CHUNK_SIZE, file.size);
        const chunk = file.slice(start, end);

        // 读取分块
        const chunkData = await readFileAsArrayBuffer(chunk);

        // 加密分块
        const encrypted = await window.crypto.subtle.encrypt(
            {
                name: "AES-GCM",
                iv: iv,
                additionalData: new TextEncoder().encode(`chunk-${i}`)
            },
            aesKey,
            chunkData
        );

        encryptedChunks.push(new Uint8Array(encrypted));

        // 更新进度
        if (onProgress) {
            onProgress(Math.round((i + 1) / totalChunks * 100));
        }
    }

    return { encryptedChunks, iv };
}

/**
 * 分块解密大文件
 * @param {Array<Uint8Array>} encryptedChunks
 * @param {CryptoKey} aesKey
 * @param {Uint8Array} iv
 * @param {Function} onProgress 进度回调
 * @returns {Promise<ArrayBuffer>}
 */
async function decryptFileInChunks(encryptedChunks, aesKey, iv, onProgress) {
    const decryptedChunks = [];

    for (let i = 0; i < encryptedChunks.length; i++) {
        const decrypted = await window.crypto.subtle.decrypt(
            {
                name: "AES-GCM",
                iv: iv,
                additionalData: new TextEncoder().encode(`chunk-${i}`)
            },
            aesKey,
            encryptedChunks[i]
        );

        decryptedChunks.push(new Uint8Array(decrypted));

        if (onProgress) {
            onProgress(Math.round((i + 1) / encryptedChunks.length * 100));
        }
    }

    // 合并所有分块
    const totalLength = decryptedChunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const result = new Uint8Array(totalLength);
    let offset = 0;

    for (const chunk of decryptedChunks) {
        result.set(chunk, offset);
        offset += chunk.length;
    }

    return result.buffer;
}

// ==================== RSA 加密 AES 密钥 ====================

/**
 * 使用公钥加密 AES 密钥
 * @param {CryptoKey} aesKey
 * @param {CryptoKey} publicKey
 * @returns {Promise<ArrayBuffer>}
 */
async function encryptAESKeyWithRSA(aesKey, publicKey) {
    const exportedAESKey = await window.crypto.subtle.exportKey("raw", aesKey);

    return await window.crypto.subtle.encrypt(
        {
            name: "RSA-OAEP"
        },
        publicKey,
        exportedAESKey
    );
}

/**
 * 使用私钥解密 AES 密钥
 * @param {ArrayBuffer} encryptedAESKey
 * @param {CryptoKey} privateKey
 * @returns {Promise<CryptoKey>}
 */
async function decryptAESKeyWithRSA(encryptedAESKey, privateKey) {
    const decryptedKey = await window.crypto.subtle.decrypt(
        {
            name: "RSA-OAEP"
        },
        privateKey,
        encryptedAESKey
    );

    return await window.crypto.subtle.importKey(
        "raw",
        decryptedKey,
        {
            name: "AES-GCM",
            length: 256
        },
        true,
        ["encrypt", "decrypt"]
    );
}

// ==================== 工具函数 ====================

/**
 * ArrayBuffer 转 Base64
 * @param {ArrayBuffer} buffer
 * @returns {string}
 */
function arrayBufferToBase64(buffer) {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return window.btoa(binary);
}

/**
 * Base64 转 ArrayBuffer
 * @param {string} base64
 * @returns {ArrayBuffer}
 */
function base64ToArrayBuffer(base64) {
    const binaryString = window.atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
}

/**
 * 下载私钥文件
 * @param {string} privateKeyPem
 * @param {string} filename
 */
function downloadPrivateKey(privateKeyPem, filename = "private_key.pem") {
    const blob = new Blob([privateKeyPem], { type: "text/plain" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    console.log(`✅ 私钥已下载: ${filename}`);
}

/**
 * 下载文件
 * @param {Blob} blob
 * @param {string} filename
 */
function downloadFile(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    console.log(`✅ 文件已下载: ${filename}`);
}

/**
 * 读取文件为 ArrayBuffer
 * @param {File} file
 * @returns {Promise<ArrayBuffer>}
 */
function readFileAsArrayBuffer(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsArrayBuffer(file);
    });
}

/**
 * 读取文件为文本
 * @param {File} file
 * @returns {Promise<string>}
 */
function readFileAsText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsText(file);
    });
}

/**
 * 格式化文件大小
 * @param {number} bytes
 * @returns {string}
 */
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

console.log("🔐 加密工具库已加载");