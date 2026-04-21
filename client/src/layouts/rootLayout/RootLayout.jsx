import './rootLayout.css';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { SignedIn, SignedOut, UserButton } from '@clerk/clerk-react';
import { useState, useEffect } from 'react';

const RootLayout = () => {
    const location = useLocation();
    const [isTransitioning, setIsTransitioning] = useState(false);
    
    useEffect(() => {
        setIsTransitioning(true);
        const timer = setTimeout(() => {
            setIsTransitioning(false);
        }, 500); // إظهار اللوجو لمدة نصف ثانية عند التنقل
        return () => clearTimeout(timer);
    }, [location.pathname]);
    
    return (
        <div className='rootLayout'>
            {isTransitioning && (
                <div className="global-logo-loader">
                    <div className="logo-spinner-wrapper">
                        <div className="spinner-ring"></div>
                        <img src="/logo.png" alt="Loading" className="spinner-logo" />
                    </div>
                </div>
            )}
            <header>
                <Link to="/" className="logo">
                    <img src="/logo.png" alt="" />
                    <span>Structra</span>
                </Link>
                <div className="user">
                    <SignedIn>
                        <UserButton afterSignOutUrl="/" />
                    </SignedIn>
                    <SignedOut>
                        <Link to="/sign-in" className="sign-in-btn">Sign In</Link>
                    </SignedOut>
                </div>
            </header>
            <main>
                <Outlet />   
            </main>
        </div>
    );
};
export default RootLayout;