/*
Fleet Tracker Backend Server

Node.js + Express server used to manage GPS tracking devices.
Provides REST API endpoints for adding, updating, searching,
and deleting tracker devices stored in a SQL Server database.

Sensitive credentials and server configuration have been removed
for security before publishing this code.
*/

const express = require('express');
const sql = require('mssql');
const cors = require('cors');
const path = require('path');
const os = require('os');

const app = express();
const port = 3000;

// Get server IP for display
function getServerIP() {
    const interfaces = os.networkInterfaces();
    for (const name in interfaces) {
        for (const iface of interfaces[name]) {
            if (iface.family === 'IPv4' && !iface.internal) {
                return iface.address;
            }
        }
    }
    return 'SERVER_IP';
}

const SERVER_IP = getServerIP();

// CORS configuration
const corsOptions = {
    origin: 'http://localhost:3000',
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Auth-Token'],
    credentials: true
};

app.use(cors(corsOptions));
app.options('*', cors(corsOptions));

// Middleware
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Log requests
app.use((req, res, next) => {
    console.log(`${new Date().toISOString()} - ${req.method} ${req.url}`);
    next();
});

// Login endpoint
app.post('/api/login', (req, res) => {
    const { username, password } = req.body;

    if (username === 'admin' && password === 'PASSWORD_PLACEHOLDER') {
        res.json({
            success: true,
            token: 'token-' + Date.now()
        });
    } else {
        res.status(401).json({
            success: false,
            error: 'Invalid credentials'
        });
    }
});

// Test endpoint
app.get('/api/test', (req, res) => {
    res.json({
        success: true,
        message: 'Server is working',
        time: new Date().toISOString()
    });
});

// Serve HTML pages
app.get('/login-page.html', (req, res) => {
    res.sendFile(path.join(__dirname, 'login-page.html'));
});

app.get('/deviceList.html', (req, res) => {
    res.sendFile(path.join(__dirname, 'deviceList.html'));
});

app.get('/index.html', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Authentication middleware
const requireAuth = (req, res, next) => {
    if (req.path === '/login-page.html' || req.path.startsWith('/api/')) {
        return next();
    }

    const token = req.headers['x-auth-token'];
    if (token) {
        next();
    } else {
        res.redirect('/login-page.html');
    }
};

app.use(['/deviceList.html', '/index.html'], requireAuth);

// SQL Server configuration
const config = {
    user: process.env.DB_USER || 'DB_USERNAME',
    password: process.env.DB_PASSWORD || 'DB_PASSWORD',
    server: process.env.DB_SERVER || 'SQL_SERVER_ADDRESS',
    database: 'GpsLocator',
    port: 1433,
    options: {
        encrypt: false,
        trustServerCertificate: true,
        enableArithAbort: true
    }
};

// Connect to SQL Server
sql.connect(config).then(pool => {
    console.log('Connected to SQL Server');
    app.locals.db = pool;
}).catch(err => {
    console.error('Database connection failed:', err);
    process.exit(1);
});

// Add device endpoint
app.post('/api/add-device', async (req, res) => {
    try {
        const {
            customerName,
            unitId,
            vendor,
            model,
            imei,
            serialNumber,
            simIccid,
            simMsisdn,
            firmwareVersion,
            hardwareVersion,
            notes
        } = req.body;

        const pool = req.app.locals.db;

        const result = await pool.request()
            .input('customerName', sql.NVarChar, customerName)
            .input('unitId', sql.NVarChar, unitId)
            .input('vendor', sql.NVarChar, vendor)
            .input('model', sql.NVarChar, model)
            .input('imei', sql.NVarChar, imei)
            .input('serialNumber', sql.NVarChar, serialNumber)
            .input('simIccid', sql.NVarChar, simIccid)
            .input('simMsisdn', sql.NVarChar, simMsisdn)
            .input('firmwareVersion', sql.NVarChar, firmwareVersion)
            .input('hardwareVersion', sql.NVarChar, hardwareVersion)
            .input('notes', sql.NVarChar, notes)
            .query(`
                INSERT INTO CustomerDevices (
                    CustomerName, UnitId, Vendor, Model, IMEI,
                    SerialNumber, SimIccid, SimMsisdn, FirmwareVersion,
                    HardwareVersion, Notes, CreatedAt
                ) VALUES (
                    @customerName, @unitId, @vendor, @model, @imei,
                    @serialNumber, @simIccid, @simMsisdn, @firmwareVersion,
                    @hardwareVersion, @notes, GETDATE()
                );
                SELECT SCOPE_IDENTITY() AS Id;
            `);

        res.json({
            success: true,
            message: 'Device added successfully',
            id: result.recordset[0].Id
        });

    } catch (error) {
        console.error('Error adding device:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to add device'
        });
    }
});

// Get devices endpoint
app.get('/api/devices', async (req, res) => {
    try {
        const searchQuery = req.query.q || '';
        const pool = req.app.locals.db;

        let query;
        let request = pool.request();

        if (searchQuery) {
            query = `
                SELECT * FROM CustomerDevices
                WHERE CustomerName LIKE @search
                OR UnitId LIKE @search
                OR Vendor LIKE @search
                OR Model LIKE @search
                OR IMEI LIKE @search
                OR SerialNumber LIKE @search
                OR SimIccid LIKE @search
                ORDER BY CreatedAt DESC
            `;
            request.input('search', sql.NVarChar, `%${searchQuery}%`);
        } else {
            query = 'SELECT * FROM CustomerDevices ORDER BY CreatedAt DESC';
        }

        const result = await request.query(query);
        res.json(result.recordset);

    } catch (error) {
        console.error('Error fetching devices:', error);
        res.status(500).json({ error: 'Failed to fetch devices' });
    }
});

// Start server
app.listen(port, '0.0.0.0', () => {
    console.log('\n=================================');
    console.log(`SERVER IS RUNNING`);
    console.log(`=================================`);
    console.log(`Local access: http://localhost:${port}`);
    console.log(`Network access: http://${SERVER_IP}:${port}`);
    console.log(`Test API: http://${SERVER_IP}:${port}/api/test`);
    console.log(`=================================\n`);
});