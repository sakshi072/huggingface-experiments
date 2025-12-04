import React from "react";

interface ConfirmationModalProps {
    isOpen:boolean;
    title:string;
    message:string;
    confirmText?:string;
    cancelText?:string;
    onConfirm: () => void;
    onCancel: () => void;
    isDestructive: boolean;
}

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
    isOpen,
    title,
    message,
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    onConfirm,
    onCancel,
    isDestructive
}) => {
    if(!isOpen) return null;

    return (
        <>
            {/* Backdrop */}
            <div
                className="fixed inset-0 bg-black bg-opacity-50 z-40 transition-opacity"
                onClick={onCancel}
            />

            {/* Modal */}
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                <div
                    className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 transform transition-all"
                    onClick={(e) => e.stopPropagation()}
                >
                  {/* Header */}
                    <div className="flex items-start gap-4 mb-4">
                        {isDestructive ? (
                            <div className="flex-shrink-0 w-12 h-12 rounded-full bg-red-100 flex items-center justify-center">
                                <svg className="w-6 h-6 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                                </svg>
                            </div>
                        ) : (
                            <div className="flex-shrink-0 w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
                                <svg className="w-6 h-6 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                </svg>
                            </div>
                        )}
                        <div className="flex-1">
                            <h3 className="text-lg font-semibold text-gray-900 mb-1">
                                {title}
                            </h3>
                            <p className="text-sm text-gray-600">
                                {message}
                            </p>
                        </div>
                    </div>

                    {/* Actions */}
                    <div className="flex fap-3 justify-end mt-6">
                        <button
                            onClick={onCancel}
                            className="px-4 py-2 text-sm font-medium text-gray-700 bg-grap-100 rounded-leg hover:bg-grap-200 transition-colors"
                        >
                            {cancelText}
                        </button>
                        <button 
                            onClick={onConfirm}
                            className={`px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors ${
                                isDestructive
                                  ? 'bg-red-600 hover:bg-red-700'
                                  : 'bg-blue-600 hover:bg-blue-700'
                              }`}
                        >
                            {confirmText}
                        </button>
                    </div>
                </div>
            </div>

        </>
    )
}