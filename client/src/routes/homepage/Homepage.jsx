import './homepage.css';
import { Link } from "react-router-dom";
import { TypeAnimation } from 'react-type-animation';
import { useState } from "react";


const Homepage = () => {
    const [typingStatus, setTypingStatus] = useState("human1");

    return (
        <div className='homepage'>
            <img src="/orbital.png" alt="Orbital Background" className='orbital' />
            
            <div className="left">
                <h1><h1>Structranet AI</h1>  </h1>
                <h2>Design. Simulate. Deploy.</h2>

                <div className="description">
                    <h5>Design complex network topologies with ease.</h5>
                    <h5>Validate and deploy them automatically with Structranet.</h5>
                </div>

                <Link to="/dashboard" className="get-started-btn">Get Started</Link>
            </div>
            
            <div className="right">
                <div className="imgContainer">
                    <div className="bgContainer">
                        <div className="bg"></div>
                    </div>
                    <img src="/bot.png" alt="" className="bot" />
                    <div className="chat">
                        <img src={typingStatus == "human1" ? "/human1.jpeg" :
                            typingStatus == "human2" ? "/human2.jpeg" : "/logo.png"} alt="" />
                        <TypeAnimation
                            sequence={[
                                
                                'human1:We produce food for Mice',
                                1000,
                                () => {
                                    setTypingStatus("Structra")
                                },
                                'Structra:We produce food for Hamsters',
                                1000,
                                () => {
                                    setTypingStatus("human2")
                                },
                                'human2:We produce food for Guinea Pigs',
                                1000,
                                () => {
                                    setTypingStatus("Structra")
                                },
                                
                                'Structra:We produce food for Chinchillas',
                                1000,
                                () => {
                                    setTypingStatus("human1")
                                },

                            ]}
                            
                            
                        />
                        
                    </div>
                </div>
            </div>
            
                       
        </div>
                
            
    );
};
export default Homepage