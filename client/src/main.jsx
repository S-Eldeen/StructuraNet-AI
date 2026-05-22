import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

import Homepage from "./routes/homepage/Homepage";
import DashboardPage from "./routes/dashboardPage/DashboardPage";
import Chatpage from "./routes/chatPage/ChatPage";
import RootLayout from "./layouts/rootLayout/RootLayout";
import DashboardLayout from "./layouts/dashboardLayout/DashboardLayout";
import SignInPage from "./routes/signInPage/signInPage";
import SignUpPage from "./routes/signUpPage/signUpPage";

import UpgradePage from "./routes/upgradePage/UpgradePage";
import CheckoutPage from "./routes/checkoutPage/CheckoutPage";
import AboutPage from "./routes/aboutPage/AboutPage";
import ContactPage from "./routes/contactPage/ContactPage";

// ✅ Security Page
import SecurityPage from "./routes/securityPage/SecurityPage";

const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { path: "/", element: <Homepage /> },
      { path: "/sign-in/*", element: <SignInPage /> },
      { path: "/sign-up/*", element: <SignUpPage /> },
      { path: "/upgrade", element: <UpgradePage /> },
      { path: "/about", element: <AboutPage /> },
      { path: "/contact", element: <ContactPage /> },
      { path: "/checkout/go", element: <CheckoutPage /> },
      { path: "/checkout/plus", element: <CheckoutPage /> },
      { path: "/checkout/pro", element: <CheckoutPage /> },
      {
        element: <DashboardLayout />,
        children: [
          { path: "/dashboard", element: <DashboardPage /> },
          { path: "/dashboard/chats/:id", element: <Chatpage /> },
          // ✅ جوا DashboardLayout — بس الـ CSS position:fixed هيغطي كل حاجة
          { path: "/dashboard/security", element: <SecurityPage /> },
        ],
      },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
