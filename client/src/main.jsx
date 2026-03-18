import React from "react";
import ReactDOM from "react-dom/client";
import './index.css';
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { ClerkProvider } from '@clerk/clerk-react';

import Homepage from "./routes/homepage/Homepage";
import DashboardPage from "./routes/dashboardPage/DashboardPage";
import Chatpage from "./routes/chatPage/ChatPage";
import RootLayout from "./layouts/rootLayout/RootLayout";
import DashboardLayout from "./layouts/dashboardLayout/DashboardLayout";
import SignInPage from "./routes/signInPage/signInPage";
import SignUpPage from "./routes/signUpPage/signUpPage";

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

if (!PUBLISHABLE_KEY) {
  throw new Error("Missing Clerk Publishable Key");
}

const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      {
        path: '/',
        element: <Homepage />
      },
      {
        path: '/sign-in/*',          // ✅ يغطي جميع المسارات الفرعية
        element: <SignInPage />
      },
      {
        path: '/sign-up/*',          // ✅ يغطي جميع المسارات الفرعية
        element: <SignUpPage />
      },
      {
        element: <DashboardLayout />,
        children: [
          {
            path: '/dashboard',
            element: <DashboardPage />
          },
          {
            path: '/dashboard/chats/:id',
            element: <Chatpage />
          }
        ]
      }
    ]
  }
]);

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ClerkProvider publishableKey={PUBLISHABLE_KEY}>
      <RouterProvider router={router} />
    </ClerkProvider>
  </React.StrictMode>
);