import './rootLayout.css';
import { Link, Outlet } from 'react-router-dom';
import { SignedIn, SignedOut, UserButton } from '@clerk/clerk-react';

const RootLayout = () => {
    return (
        <div className='rootLayout'>
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