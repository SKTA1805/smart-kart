const express = require("express");

const cors = require("cors");

const bodyParser = require("body-parser");

const path = require("path");

const { jsPDF } = require("jspdf");

require("jspdf-autotable");

const http = require("http");

const WebSocket = require("ws");

const crypto = require("crypto");

require("dotenv").config();

const Razorpay = require("razorpay");



const app = express();

const server = http.createServer(app);

const wss = new WebSocket.Server({ server });



const PORT = 5000;



app.use(cors());

app.use(bodyParser.json());

app.use(express.static("public")); // Serve static files



let cart = [];



// WebSocket Broadcast Function

function broadcastCartUpdate() {

  wss.clients.forEach((client) => {

    if (client.readyState === WebSocket.OPEN) {

      client.send("update_cart");

    }

  });

}



// Serve the main HTML file

app.get("/", (req, res) => {

  res.sendFile(path.join(__dirname, "public", "index.html"));

});



// Update cart endpoint that accepts { name, price } from your QR scanner

app.post("/update-cart", (req, res) => {

  const { name, price } = req.body;

  if (!name || !price) {

    return res.status(400).json({ success: false, message: "Invalid product data" });

  }

  // Use the product name as the unique identifier

  const product = cart.find((item) => item.name === name);

  if (product) {

    product.quantity += 1;

  } else {

    cart.push({ tag: name, name: name, price: parseFloat(price), quantity: 1 });

  }

  broadcastCartUpdate(); // Notify WebSocket clients of update

  res.json({ success: true, message: "Cart updated", cart });

});



// Get cart items

app.get("/cart", (req, res) => {

  res.json(cart);

});



// Remove item from cart (Decrease quantity instead of removing completely)

app.post("/remove-item", (req, res) => {

  const { tag } = req.body;

  const productIndex = cart.findIndex((item) => item.tag === tag);

  if (productIndex !== -1) {

    if (cart[productIndex].quantity > 1) {

      cart[productIndex].quantity -= 1;

    } else {

      cart.splice(productIndex, 1);

    }

  }

  res.json({ success: true, message: "Item updated", cart });

});



// Generate PDF Bill

app.get("/generate-bill", (req, res) => {

  const doc = new jsPDF();

  let totalQuantity = 0;

  let total = 0;



  // Header text setup

  doc.setFont("Helvetica", "bold");

  doc.setFontSize(14);



  if (cart.length === 0) {

    doc.text("Your cart is empty", 20, 20);

  } else {

    // Load a stylish font (ensure the font file exists in your project)

    doc.addFont("GreatVibes-Regular.ttf", "GreatVibes", "normal");

    doc.setFont("GreatVibes");

    doc.setFontSize(22);



    doc.setFont("Helvetica", "bold");

    doc.setFontSize(16);

    const pageWidth = doc.internal.pageSize.getWidth();

    const text = "Your Bill";

    const textWidth = doc.getTextWidth(text);

    const centerX = (pageWidth - textWidth) / 2;

    doc.text(text, centerX, 20);

    const tableData = cart.map((item) => {

      const subtotal = item.quantity * item.price;

      totalQuantity += item.quantity;

      total += subtotal;

      return [item.name, `${item.price} Rs`, item.quantity, `${subtotal} Rs`];

    });



    doc.autoTable({

      head: [["Product", "Price", "Quantity", "Subtotal"]],

      body: tableData,

      startY: 30,

    });

    let finalY = doc.lastAutoTable.finalY + 10;

    doc.text(`Total Qty: ${totalQuantity}`, 20, finalY);

    doc.text(`Total Amt: ${total}.00 Rs`, 20, finalY + 10);



    // Add "Thank you" message in a stylish font

    doc.setFont("GreatVibes");

    doc.setFontSize(18);

    const thankYouText = "Thank you for visiting us!";

    const thankYouTextWidth = doc.getTextWidth(thankYouText);

    const thankYouX = (pageWidth - thankYouTextWidth) / 2;

    doc.text(thankYouText, thankYouX, finalY + 30);

  }



  res.setHeader("Content-Type", "application/pdf");

  res.setHeader("Content-Disposition", 'attachment; filename="bill.pdf"');

  res.send(Buffer.from(doc.output("arraybuffer")));

});



// Create Order API (for payment via Razorpay)

app.post("/create-order", async (req, res) => {

  try {

    const { amount } = req.body; // Amount in INR

    const options = {

      amount: amount * 100, // Convert to paise

      currency: "INR",

      receipt: `receipt_${Date.now()}`,

    };

    const order = await Razorpay.orders.create(options);

    res.json({ success: true, orderId: order.id, amount: order.amount });

  } catch (error) {

    console.error("Error creating order:", error);

    res.status(500).json({ success: false, error: error.message });

  }

});



// Verify Payment API (Razorpay webhook or frontend calls this after payment)

app.post("/verify-payment", async (req, res) => {

  const { razorpay_order_id, razorpay_payment_id, razorpay_signature } = req.body;

  const generated_signature = crypto

    .createHmac("sha256", process.env.RAZORPAY_KEY_SECRET)

    .update(`${razorpay_order_id}|${razorpay_payment_id}`)

    .digest("hex");



  if (generated_signature === razorpay_signature) {

    console.log("Payment Verified Successfully");

    res.json({ success: true, message: "Payment Successful!", paymentId: razorpay_payment_id });

  } else {

    res.status(400).json({ success: false, message: "Payment Verification Failed" });

  }

});



// Start the server with WebSocket integration

server.listen(PORT, () => console.log(`Server running on http://smart-kart.onrender.com:${PORT}`));

