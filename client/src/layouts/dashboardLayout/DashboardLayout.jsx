import { Outlet, useNavigate } from 'react-router-dom';
import './dashboardLayout.css';
import ChatList from "../../components/chatList/ChatList";
import { useAuth } from '@clerk/clerk-react';
import { useEffect, useState } from 'react';

const DashboardLayout = () => {
    const { userId, isLoaded } = useAuth();
    const navigate = useNavigate();

    // ✅ إضافة جديدة (بدون التأثير على القديم)
    const [collapsed, setCollapsed] = useState(false);

    useEffect(() => {
        if (isLoaded && !userId) {
            navigate('/sign-in');
        }
    }, [isLoaded, userId, navigate]);

    // ✅ احتفظنا بالـ loader الأفضل من الكود الأول
    if (!isLoaded) return (
        <div className="global-logo-loader">
            <div className="logo-spinner-wrapper">
                <div className="spinner-ring"></div>
                <img src="/logo.png" alt="Loading" className="spinner-logo" />
            </div>
        </div>
    );

    return (
        <div className='dashboardLayout'>

            {/* ✅ menu مع collapse */}
            <div className={`menu ${collapsed ? "collapsed" : ""}`}>
                <ChatList />
            </div>

            <div className="content">

                {/* ✅ زرار جديد فقط */}
                <button
                    className="sidebar-toggle-btn"
                    onClick={() => setCollapsed(!collapsed)}
                >
                    ☰
                </button>

                <Outlet />
            </div>
        </div>
    );
};

export default DashboardLayout;
